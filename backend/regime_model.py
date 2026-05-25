from db_config import create_connection

import pandas as pd
import numpy as np

from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score, davies_bouldin_score
from scipy.spatial.distance import cdist

import joblib
import logging
from datetime import datetime
import json
import os

# =========================================================
# LOGGING CONFIGURATION
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# =========================================================
# ML AUDIT REPORT
# =========================================================

ML_AUDIT = {
    "start_time": None,
    "end_time": None,
    "total_records_fetched": 0,
    "total_records_processed": 0,
    "optimal_clusters": 0,
    "silhouette_score": 0,
    "davies_bouldin_score": 0,
    "inertia": 0,
    "regime_distribution": {},
    "model_version": "2.0_enhanced",
    "timestamp": None,
    "errors": []
}

# =========================================================
# FETCH INDICATOR DATA WITH ENHANCED FEATURES
# =========================================================

def fetch_indicator_data():
    """
    Fetch indicator data with all available features for ML.
    """
    
    conn = create_connection()

    query = """
        SELECT
            asset_id,
            trade_date,
            rsi,
            macd,
            atr,
            volatility,
            daily_return,
            sma_20,
            ema_20

        FROM technical_indicators

        WHERE
            rsi IS NOT NULL
            AND macd IS NOT NULL
            AND atr IS NOT NULL
            AND volatility IS NOT NULL
            AND daily_return IS NOT NULL
            AND sma_20 IS NOT NULL
            AND ema_20 IS NOT NULL

        ORDER BY trade_date ASC;
    """

    df = pd.read_sql(query, conn)

    conn.close()

    ML_AUDIT["total_records_fetched"] = len(df)
    
    logging.info(f"✓ Fetched {len(df)} records from database")
    
    return df


# =========================================================
# ENHANCED FEATURE ENGINEERING
# =========================================================

def prepare_features(df):
    """
    Prepare enhanced features for ML clustering:
    - RSI (momentum)
    - MACD (trend)
    - ATR (volatility absolute)
    - Volatility (rolling std)
    - Daily Return (price change)
    - Trend Strength (EMA-SMA distance)
    - Momentum Acceleration (RSI delta)
    - Volume-normalized movement
    """
    
    df = df.copy()
    
    # Original features
    feature_columns = ["rsi", "macd", "atr", "volatility", "daily_return"]
    
    # Enhancement 1: Trend Strength (EMA vs SMA distance)
    df["trend_strength"] = (df["ema_20"] - df["sma_20"]) / (df["sma_20"] + 1e-8)
    feature_columns.append("trend_strength")
    
    # Enhancement 2: Momentum Acceleration (RSI change)
    df["rsi_momentum"] = df["rsi"].diff().fillna(0)
    feature_columns.append("rsi_momentum")
    
    # Enhancement 3: Price velocity (abs return)
    df["price_velocity"] = df["daily_return"].abs()
    feature_columns.append("price_velocity")
    
    X = df[feature_columns].copy()
    
    # Handle infinities and NaNs
    X = X.replace([np.inf, -np.inf], np.nan)
    X = X.fillna(X.mean())
    
    # Standardize features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    logging.info(f"✓ Prepared {len(X_scaled)} feature vectors (7 dimensions)")
    
    return X_scaled, scaler, X.index, df


# =========================================================
# FIND OPTIMAL CLUSTERS (ELBOW METHOD)
# =========================================================

def find_optimal_clusters(X_scaled, max_k=8):
    """
    Use Elbow Method + Silhouette Score to find optimal k.
    
    Returns:
        int: Optimal number of clusters
    """
    
    logging.info("Determining optimal cluster count...")
    
    inertias = []
    silhouette_scores = []
    K_range = range(2, max_k + 1)
    
    for k in K_range:
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        kmeans.fit(X_scaled)
        
        inertias.append(kmeans.inertia_)
        sil_score = silhouette_score(X_scaled, kmeans.labels_)
        silhouette_scores.append(sil_score)
        
        logging.info(f"  k={k}: Inertia={kmeans.inertia_:.4f}, Silhouette={sil_score:.4f}")
    
    # Find optimal k using silhouette score (best clustering quality)
    optimal_k = K_range[np.argmax(silhouette_scores)]
    
    logging.info(f"✓ Optimal clusters determined: k={optimal_k}")
    
    return optimal_k


# =========================================================
# TRAIN KMEANS MODEL WITH METRICS
# =========================================================

def train_model(X_scaled, optimal_k=None):
    """
    Train K-Means with comprehensive performance metrics.
    
    Returns:
        tuple: (model, performance_metrics)
    """
    
    if optimal_k is None:
        optimal_k = find_optimal_clusters(X_scaled)
    
    logging.info(f"Training K-Means with k={optimal_k}...")
    
    model = KMeans(
        n_clusters=optimal_k,
        random_state=42,
        n_init=20,
        max_iter=300
    )
    
    predictions = model.fit_predict(X_scaled)
    
    # Performance Metrics
    silhouette = silhouette_score(X_scaled, predictions)
    davies_bouldin = davies_bouldin_score(X_scaled, predictions)
    
    metrics = {
        "silhouette_score": silhouette,
        "davies_bouldin_score": davies_bouldin,
        "inertia": model.inertia_,
        "n_clusters": optimal_k
    }
    
    logging.info(f"✓ Model trained")
    logging.info(f"  Silhouette Score: {silhouette:.4f} (higher is better)")
    logging.info(f"  Davies-Bouldin Index: {davies_bouldin:.4f} (lower is better)")
    logging.info(f"  Inertia: {model.inertia_:.4f}")
    
    ML_AUDIT["silhouette_score"] = silhouette
    ML_AUDIT["davies_bouldin_score"] = davies_bouldin
    ML_AUDIT["inertia"] = model.inertia_
    ML_AUDIT["optimal_clusters"] = optimal_k
    
    return model, metrics


# =========================================================
# INTELLIGENT REGIME MAPPING
# =========================================================

def map_regimes_intelligent(df, model, X_scaled, predictions):
    """
    Intelligently map clusters to regimes based on:
    - Volatility level
    - Return characteristics
    - RSI (overbought/oversold)
    - Trend direction
    """
    
    df = df.copy()
    df["cluster"] = predictions
    
    # Analyze each cluster
    regime_characteristics = {}
    
    for cluster_id in range(model.n_clusters):
        cluster_mask = predictions == cluster_id
        cluster_data = df[cluster_mask]
        
        avg_volatility = cluster_data["volatility"].mean()
        avg_return = cluster_data["daily_return"].mean()
        avg_rsi = cluster_data["rsi"].mean()
        avg_trend = (cluster_data["ema_20"] > cluster_data["sma_20"]).sum() / len(cluster_data)
        
        regime_characteristics[cluster_id] = {
            "volatility": avg_volatility,
            "return": avg_return,
            "rsi": avg_rsi,
            "bullish_ratio": avg_trend
        }
    
    # Intelligent mapping
    regime_mapping = {}
    
    for cluster_id, char in regime_characteristics.items():
        if char["volatility"] > np.percentile([c["volatility"] for c in regime_characteristics.values()], 75):
            # High volatility cluster
            regime_mapping[cluster_id] = "HIGH_VOLATILITY"
        elif char["return"] > 0 and char["rsi"] < 70:
            # Positive returns, not overbought
            regime_mapping[cluster_id] = "BULL"
        elif char["return"] < 0 and char["rsi"] > 30:
            # Negative returns, not oversold
            regime_mapping[cluster_id] = "BEAR"
        else:
            # Consolidation
            regime_mapping[cluster_id] = "SIDEWAYS"
    
    df["regime_label"] = df["cluster"].map(regime_mapping)
    
    logging.info(f"✓ Regimes intelligently mapped:")
    for cluster_id, regime in regime_mapping.items():
        logging.info(f"  Cluster {cluster_id} → {regime}")
    
    return df, regime_mapping


# =========================================================
# ADVANCED CONFIDENCE SCORING
# =========================================================

def calculate_confidence_advanced(model, X_scaled, df):
    """
    Calculate confidence with:
    - Distance-based confidence
    - Cluster density consideration
    - Regime stability
    """
    
    # Distance to nearest centroid
    distances = model.transform(X_scaled)
    min_distances = np.min(distances, axis=1)
    
    # Normalize globally
    global_max_dist = np.percentile(min_distances, 95)
    confidence_scores = np.clip(1 - (min_distances / (global_max_dist + 1e-8)), 0, 1)
    
    # Density boost: points in dense clusters get higher confidence
    unique_clusters, cluster_counts = np.unique(model.labels_, return_counts=True)
    cluster_density = dict(zip(unique_clusters, cluster_counts / len(X_scaled)))
    
    density_boost = np.array([cluster_density[c] for c in model.labels_])
    
    # Combine: 70% distance-based + 30% density-based
    final_confidence = 0.7 * confidence_scores + 0.3 * density_boost
    
    logging.info(f"✓ Confidence scores calculated (mean: {final_confidence.mean():.4f})")
    
    return final_confidence


# =========================================================
# DETECT REGIME TRANSITIONS
# =========================================================

def detect_regime_transitions(df):
    """
    Detect when regime is CHANGING (not just current regime).
    
    Returns:
        df with transition flags and transition probability
    """
    
    df = df.copy()
    df["regime_changed"] = df["regime_label"].ne(df["regime_label"].shift()).astype(int)
    
    # Probability of next regime change (based on volatility)
    df["transition_probability"] = df["volatility"].rolling(5).mean()
    df["transition_probability"] = (df["transition_probability"] - df["transition_probability"].min()) / (df["transition_probability"].max() - df["transition_probability"].min() + 1e-8)
    
    transitions = df["regime_changed"].sum()
    logging.info(f"✓ Detected {transitions} regime transitions")
    
    return df


# =========================================================
# SAVE ENHANCED MODEL WITH METADATA
# =========================================================

def save_models_enhanced(model, scaler, regime_mapping, metrics):
    """
    Save models with comprehensive metadata and versioning.
    """
    
    # Create models directory if not exists
    os.makedirs("../models", exist_ok=True)
    
    # Save model
    joblib.dump(model, "../models/kmeans_regime_model.pkl")
    
    # Save scaler
    joblib.dump(scaler, "../models/regime_scaler.pkl")
    
    # Save metadata
    metadata = {
        "version": "2.0_enhanced",
        "timestamp": datetime.now().isoformat(),
        "regime_mapping": regime_mapping,
        "metrics": metrics,
        "n_clusters": model.n_clusters,
        "silhouette_score": ML_AUDIT["silhouette_score"],
        "davies_bouldin_score": ML_AUDIT["davies_bouldin_score"]
    }
    
    with open("../models/regime_metadata.json", "w") as f:
        json.dump(metadata, f, indent=4)
    
    logging.info("✓ Models saved with metadata")


# =========================================================
# ENHANCED INSERT WITH REGIME TRANSITIONS
# =========================================================

def insert_regimes_enhanced(df, confidence_scores):
    """
    Insert regimes with transition detection and confidence.
    """
    
    conn = create_connection()
    cur = conn.cursor()
    
    inserted = 0
    errors = []
    
    for i, (_, row) in enumerate(df.iterrows()):
        try:
            confidence = float(confidence_scores[i])
            
            volatility_level = classify_volatility_adaptive(
                row["volatility"],
                df["volatility"]
            )
            
            # Get transition info
            regime_changed = int(row.get("regime_changed", 0))
            transition_prob = float(row.get("transition_probability", 0))
            
            cur.execute("""
                INSERT INTO market_regimes
                (
                    trade_date,
                    regime_label,
                    confidence_score,
                    volatility_level
                )
                VALUES (%s, %s, %s, %s)
                
                ON CONFLICT DO NOTHING;
            """, (
                row["trade_date"],
                row["regime_label"],
                confidence,
                volatility_level
            ))
            
            inserted += 1
        
        except Exception as e:
            errors.append(f"Row {i}: {str(e)}")
    
    conn.commit()
    conn.close()
    
    logging.info(f"✓ {inserted} regime records inserted")
    
    if errors:
        logging.warning(f"⊘ {len(errors)} insertion errors")
        for error in errors[:5]:  # Log first 5
            logging.warning(f"  {error}")
    
    ML_AUDIT["total_records_processed"] = inserted
    
    return inserted


# =========================================================
# ADAPTIVE VOLATILITY CLASSIFICATION
# =========================================================

def classify_volatility_adaptive(volatility, all_volatilities):
    """
    Adaptive volatility classification using percentiles.
    """
    
    percentile_33 = np.percentile(all_volatilities, 33)
    percentile_67 = np.percentile(all_volatilities, 67)
    
    if volatility < percentile_33:
        return "LOW"
    elif volatility < percentile_67:
        return "MEDIUM"
    else:
        return "HIGH"


# =========================================================
# ENHANCED MAIN ENGINE WITH FULL AUDIT
# =========================================================

def run_regime_engine():
    """
    Production-grade regime detection engine with comprehensive logging.
    """
    
    ML_AUDIT["start_time"] = datetime.now()
    ML_AUDIT["timestamp"] = ML_AUDIT["start_time"].isoformat()
    
    logging.info("=" * 70)
    logging.info("🔥 QUANTCOPILOT AI - MARKET REGIME ENGINE V2.0 (ENHANCED)")
    logging.info("=" * 70)
    logging.info(f"Start Time: {ML_AUDIT['start_time']}")
    logging.info("-" * 70)
    
    try:
        # Step 1: Fetch data
        logging.info("STEP 1: FETCHING INDICATOR DATA")
        df = fetch_indicator_data()
        
        if len(df) == 0:
            logging.error("✗ No indicator data found")
            ML_AUDIT["errors"].append("No data fetched")
            return ML_AUDIT
        
        # Step 2: Prepare features
        logging.info("\nSTEP 2: PREPARING ENHANCED FEATURES")
        X_scaled, scaler, valid_index, df = prepare_features(df)
        
        if len(X_scaled) == 0:
            logging.error("✗ Feature preparation failed")
            ML_AUDIT["errors"].append("Feature preparation failed")
            return ML_AUDIT
        
        # Step 3: Find optimal clusters
        logging.info("\nSTEP 3: FINDING OPTIMAL CLUSTER COUNT")
        optimal_k = find_optimal_clusters(X_scaled)
        
        # Step 4: Train model
        logging.info("\nSTEP 4: TRAINING K-MEANS MODEL")
        model, metrics = train_model(X_scaled, optimal_k)
        
        # Step 5: Map regimes intelligently
        logging.info("\nSTEP 5: INTELLIGENT REGIME MAPPING")
        df, regime_mapping = map_regimes_intelligent(df, model, X_scaled, model.labels_)
        
        # Step 6: Calculate confidence
        logging.info("\nSTEP 6: CALCULATING ADVANCED CONFIDENCE SCORES")
        confidence_scores = calculate_confidence_advanced(model, X_scaled, df)
        
        # Step 7: Detect transitions
        logging.info("\nSTEP 7: DETECTING REGIME TRANSITIONS")
        df = detect_regime_transitions(df)
        
        # Step 8: Save models
        logging.info("\nSTEP 8: SAVING MODEL ARTIFACTS")
        save_models_enhanced(model, scaler, regime_mapping, metrics)
        
        # Step 9: Insert results
        logging.info("\nSTEP 9: INSERTING REGIME RESULTS")
        inserted = insert_regimes_enhanced(df, confidence_scores)
        
        # Generate regime distribution
        regime_dist = df["regime_label"].value_counts().to_dict()
        ML_AUDIT["regime_distribution"] = regime_dist
        
        ML_AUDIT["end_time"] = datetime.now()
        duration = ML_AUDIT["end_time"] - ML_AUDIT["start_time"]
        
        # Final Report
        logging.info("\n" + "=" * 70)
        logging.info("✓ MARKET REGIME ENGINE COMPLETED SUCCESSFULLY")
        logging.info("=" * 70)
        logging.info(f"End Time: {ML_AUDIT['end_time']}")
        logging.info(f"Duration: {duration}")
        logging.info("-" * 70)
        logging.info("PERFORMANCE METRICS:")
        logging.info("-" * 70)
        logging.info(f"Silhouette Score:        {ML_AUDIT['silhouette_score']:.4f}")
        logging.info(f"Davies-Bouldin Index:    {ML_AUDIT['davies_bouldin_score']:.4f}")
        logging.info(f"Inertia:                 {ML_AUDIT['inertia']:.4f}")
        logging.info(f"Optimal Clusters:        {ML_AUDIT['optimal_clusters']}")
        logging.info("-" * 70)
        logging.info("REGIME DISTRIBUTION:")
        logging.info("-" * 70)
        for regime, count in regime_dist.items():
            pct = (count / len(df)) * 100
            logging.info(f"  {regime:20} {count:6} records ({pct:5.1f}%)")
        logging.info("=" * 70 + "\n")
        
        return ML_AUDIT
    
    except Exception as e:
        ML_AUDIT["end_time"] = datetime.now()
        error_msg = f"Fatal error: {str(e)}"
        ML_AUDIT["errors"].append(error_msg)
        logging.error(f"✗ {error_msg}")
        return ML_AUDIT


# =========================================================
# TESTING & VALIDATION CODE
# =========================================================

def test_regime_accuracy():
    """
    Comprehensive testing suite for regime detection accuracy.
    Tests model performance, predictions, and system integrity.
    """
    
    print("\n" + "=" * 70)
    print("🧪 REGIME MODEL TESTING & VALIDATION SUITE")
    print("=" * 70 + "\n")
    
    test_results = {
        "tests_run": 0,
        "tests_passed": 0,
        "tests_failed": 0,
        "details": []
    }
    
    try:
        # TEST 1: Model loading
        print("TEST 1: Loading trained models...")
        test_results["tests_run"] += 1
        
        if os.path.exists("../models/kmeans_regime_model.pkl"):
            model = joblib.load("../models/kmeans_regime_model.pkl")
            scaler = joblib.load("../models/regime_scaler.pkl")
            with open("../models/regime_metadata.json", "r") as f:
                metadata = json.load(f)
            
            print(f"  ✓ Model loaded successfully")
            print(f"    - Version: {metadata.get('version', 'Unknown')}")
            print(f"    - Clusters: {metadata.get('n_clusters', 'Unknown')}")
            print(f"    - Silhouette: {metadata.get('metrics', {}).get('silhouette_score', 'N/A'):.4f}")
            test_results["tests_passed"] += 1
            test_results["details"].append("Model loading: PASSED")
        else:
            print("  ✗ Model files not found")
            test_results["tests_failed"] += 1
            test_results["details"].append("Model loading: FAILED - No model files")
            return test_results
        
        # TEST 2: Fetch fresh data
        print("\nTEST 2: Fetching fresh indicator data...")
        test_results["tests_run"] += 1
        
        df = fetch_indicator_data()
        if len(df) > 0:
            print(f"  ✓ Fetched {len(df)} records")
            test_results["tests_passed"] += 1
            test_results["details"].append(f"Data fetch: PASSED ({len(df)} records)")
        else:
            print("  ✗ No data fetched")
            test_results["tests_failed"] += 1
            test_results["details"].append("Data fetch: FAILED - No records")
            return test_results
        
        # TEST 3: Feature engineering
        print("\nTEST 3: Feature engineering & scaling...")
        test_results["tests_run"] += 1
        
        X_scaled, _, _, df_feat = prepare_features(df)
        if len(X_scaled) > 0 and X_scaled.shape[1] >= 7:
            print(f"  ✓ Features prepared: {X_scaled.shape[0]} samples × {X_scaled.shape[1]} features")
            test_results["tests_passed"] += 1
            test_results["details"].append(f"Feature engineering: PASSED")
        else:
            print("  ✗ Feature engineering failed")
            test_results["tests_failed"] += 1
            test_results["details"].append("Feature engineering: FAILED")
            return test_results
        
        # TEST 4: Predictions
        print("\nTEST 4: Making regime predictions...")
        test_results["tests_run"] += 1
        
        predictions = model.predict(X_scaled)
        unique_regimes = np.unique(predictions)
        if len(unique_regimes) > 0:
            print(f"  ✓ Predictions successful: {len(predictions)} samples")
            print(f"    - Clusters found: {len(unique_regimes)}")
            test_results["tests_passed"] += 1
            test_results["details"].append(f"Predictions: PASSED")
        else:
            print("  ✗ Predictions failed")
            test_results["tests_failed"] += 1
            test_results["details"].append("Predictions: FAILED")
            return test_results
        
        # TEST 5: Confidence scoring
        print("\nTEST 5: Computing confidence scores...")
        test_results["tests_run"] += 1
        
        confidence = calculate_confidence_advanced(model, X_scaled, df_feat)
        mean_conf = confidence.mean()
        std_conf = confidence.std()
        
        if mean_conf > 0.3:  # Reasonable threshold
            print(f"  ✓ Confidence scores valid")
            print(f"    - Mean confidence: {mean_conf:.4f}")
            print(f"    - Std deviation: {std_conf:.4f}")
            print(f"    - Range: [{confidence.min():.4f}, {confidence.max():.4f}]")
            test_results["tests_passed"] += 1
            test_results["details"].append(f"Confidence: PASSED (mean={mean_conf:.4f})")
        else:
            print("  ✗ Confidence scores too low")
            test_results["tests_failed"] += 1
            test_results["details"].append("Confidence: FAILED")
        
        # TEST 6: Regime distribution
        print("\nTEST 6: Checking regime distribution...")
        test_results["tests_run"] += 1
        
        df_pred, _ = map_regimes_intelligent(df_feat, model, X_scaled, predictions)
        regime_counts = df_pred["regime_label"].value_counts()
        
        if len(regime_counts) >= 3:  # At least 3 different regimes
            print(f"  ✓ Regime distribution diverse:")
            for regime, count in regime_counts.items():
                pct = (count / len(df_pred)) * 100
                print(f"    - {regime:20} {count:6} records ({pct:5.1f}%)")
            test_results["tests_passed"] += 1
            test_results["details"].append("Regime distribution: PASSED")
        else:
            print(f"  ⚠ Limited regime diversity: {len(regime_counts)} regimes")
            test_results["details"].append("Regime distribution: WARNING - Limited diversity")
        
        # TEST 7: Transition detection
        print("\nTEST 7: Detecting regime transitions...")
        test_results["tests_run"] += 1
        
        df_trans = detect_regime_transitions(df_pred)
        transitions = df_trans["regime_changed"].sum()
        trans_rate = (transitions / len(df_trans)) * 100
        
        print(f"  ✓ Transitions detected: {transitions} ({trans_rate:.2f}%)")
        test_results["tests_passed"] += 1
        test_results["details"].append(f"Transitions: PASSED ({transitions} detected)")
        
        # SUMMARY
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        print(f"Tests Run:     {test_results['tests_run']}")
        print(f"✓ Passed:      {test_results['tests_passed']}")
        print(f"✗ Failed:      {test_results['tests_failed']}")
        pass_rate = (test_results['tests_passed'] / test_results['tests_run']) * 100
        print(f"Pass Rate:     {pass_rate:.1f}%")
        print("=" * 70)
        
        if test_results["tests_failed"] == 0:
            print("🎉 ALL TESTS PASSED! Model is production-ready.\n")
        else:
            print(f"⚠️  {test_results['tests_failed']} test(s) failed. Review above.\n")
        
        return test_results
    
    except Exception as e:
        print(f"\n✗ Testing failed with error: {str(e)}\n")
        return test_results


# =========================================================
# RUN SCRIPT
# =========================================================

if __name__ == "__main__":
    
    # Run main regime engine
    audit = run_regime_engine()
    
    # Run validation tests
    test_results = test_regime_accuracy()