import os
import json

from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

from gensim.corpora import Dictionary
from gensim.models.ldamodel import LdaModel

import pacmap
import trimap

from umap import UMAP
from sklearn.manifold import TSNE


def load_dataset(path: str, start_date: datetime, end_date: datetime, count: int = 0) -> pd.DataFrame:
    with open(path, "r") as file:
        data = pd.DataFrame(json.loads(file.read()))

    data["parsed_date"] = pd.to_datetime(data["date"].apply(lambda d: datetime(d["year"], d["month"], d["day"])))
    data = data[(data["parsed_date"] >= start_date) & (data["parsed_date"] <= end_date)]
    
    if 0 < count < len(data):
        data = data.sample(count)
    
    return data, data.index.to_numpy()


def load_embeddings(path: str, idxs: np.ndarray) -> np.ndarray:
    embeddings = np.load(path)
    return embeddings[idxs]


def lda_topics(tokenized_texts: list[list[str]], num_topics: int = 10) -> tuple[list[int], LdaModel]:
    dictionary = Dictionary(tokenized_texts)
    corpus = [dictionary.doc2bow(text) for text in tokenized_texts]
    lda = LdaModel(corpus=corpus, num_topics=num_topics, id2word=dictionary, passes=8, random_state=42)

    doc_topics: list[int] = []
    for bow in corpus:
        topic_distribution = lda.get_document_topics(bow)
        dominant = max(topic_distribution, key=lambda x: x[1])[0]
        doc_topics.append(dominant)
    return doc_topics, lda


def reduce_dimensions(X: np.ndarray, method: str = "umap", params: dict = {}, n_components: int = 2) -> np.ndarray:
    if method == "umap":
        reducer = UMAP(n_components=n_components, random_state=42, **params)
    elif method == "tsne":
        reducer = TSNE(n_components=n_components, random_state=42, **params)
    elif method == "pacmap":
        reducer = pacmap.PaCMAP(n_components=n_components, **params)
    elif method == "trimap":
        reducer = trimap.TRIMAP(n_dims=n_components, **params)
    else:
        raise ValueError(f"Unknown dimensionality reduction method: {method}")
    return reducer.fit_transform(X)


def scatter_plots(df: pd.DataFrame):
    df["topic"] = pd.Categorical(df["topic"])
    topic_order = sorted(df["topic"].unique())
    col1, col2 = st.columns(2, gap="medium")

    with col1:
        fig_topic = px.scatter(
            df,
            x="x",
            y="y",
            color="topic",
            category_orders={"topic": topic_order},
            hover_data=["headline", "short_description", "date", "category"],
            height=700,
        )
        st.plotly_chart(fig_topic, use_container_width=True)

    with col2:
        fig_cat = px.scatter(
            df,
            x="x",
            y="y",
            color="category",
            hover_data=["headline", "short_description", "date", "topic"],
            height=700,
        )
        st.plotly_chart(fig_cat, use_container_width=True)


def plotly_3d_scatter(df: pd.DataFrame):
    df["topic"] = pd.Categorical(df["topic"])
    topic_order = sorted(df["topic"].unique())
    col1, col2 = st.columns(2, gap="medium")

    with col1:
        fig_topic = px.scatter_3d(
            df,
            x="x",
            y="y",
            z="z",
            color="topic",
            category_orders={"topic": topic_order},
            hover_data=["headline", "short_description", "date", "topic", "category"],
            height=700,
            opacity=0.7,
        )
        fig_topic.update_traces(marker=dict(size=4))
        st.plotly_chart(fig_topic, use_container_width=True)

    with col2:
        fig_cat = px.scatter_3d(
            df,
            x="x",
            y="y",
            z="z",
            color="category",
            hover_data=["headline", "short_description", "date", "topic", "category"],
            height=700,
            opacity=0.7,
        )
        fig_cat.update_traces(marker=dict(size=4))
        st.plotly_chart(fig_cat, use_container_width=True)


def topic_evolution_chart(df: pd.DataFrame):
    date_series = pd.to_datetime(df["date"].apply(lambda d: datetime(d["year"], d["month"], d["day"])))

    df = df.copy()
    df["month"] = date_series.dt.to_period("M").astype(str)

    monthly = df.groupby(["month", "topic"], observed=False).size().reset_index(name="count")
    total = df["month"].value_counts().rename("total").reset_index().rename(columns={"index": "month"})
    monthly = monthly.merge(total, on="month")
    monthly["share"] = monthly["count"] / monthly["total"]

    fig = px.line(
        monthly,
        x="month",
        y="share",
        color="topic",
        markers=True,
        height=500,
    )
    fig.update_layout(xaxis_title="Month", yaxis_title="Topic Share")
    st.plotly_chart(fig, use_container_width=True)


def sidebar_configuration() -> dict:
    st.sidebar.header("Configuration")

    sample_size = st.sidebar.number_input(
        "Sample size (0 = all)", min_value=0, max_value=200_000, value=20_000, step=1_000
    )

    date_range = st.sidebar.date_input(
        "Select date range",
        [min_date := datetime(2012, 1, 1), max_date := datetime(2023, 1, 1)],
        min_value=min_date,
        max_value=max_date,
    )

    dr_method = st.sidebar.selectbox(
        "Dimensionality-reduction algorithm", ["umap", "tsne", "pacmap", "trimap"], index=0
    )

    dr_params = {}
    if dr_method == "umap":
        dr_params["n_neighbors"] = st.sidebar.slider("UMAP: n_neighbors", 5, 100, 15)
        dr_params["min_dist"] = st.sidebar.slider("UMAP: min_dist", 0.0, 1.0, 0.1)
        dr_params["metric"] = st.sidebar.selectbox("UMAP: metric", ["euclidean", "manhattan", "cosine"])
    elif dr_method == "tsne":
        dr_params["perplexity"] = st.sidebar.slider("t-SNE: perplexity", 5, 50, 30)
        dr_params["learning_rate"] = st.sidebar.slider("t-SNE: learning_rate", 10, 1000, 200)
        dr_params["metric"] = st.sidebar.selectbox("t-SNE: metric", ["euclidean", "manhattan", "cosine"])
    elif dr_method == "pacmap":
        dr_params["n_neighbors"] = st.sidebar.slider("PaCMAP: n_neighbors", 5, 100, 10)
        dr_params["MN_ratio"] = st.sidebar.slider("PaCMAP: MN_ratio", 0.0, 1.0, 0.5)
        dr_params["FP_ratio"] = st.sidebar.slider("PaCMAP: FP_ratio", 1.0, 10.0, 2.0)
        dr_params["distance"] = st.sidebar.selectbox("PaCMAP: distance", ["euclidean", "manhattan", "angular"])
    elif dr_method == "trimap":
        dr_params["n_inliers"] = st.sidebar.slider("TriMAP: n_inliers", 5, 100, 10)
        dr_params["n_outliers"] = st.sidebar.slider("TriMAP: n_outliers", 1, 20, 5)
        dr_params["n_random"] = st.sidebar.slider("TriMAP: n_random", 1, 10, 3)
        dr_params["distance"] = st.sidebar.selectbox("TriMAP: distance", ["euclidean", "manhattan", "cosine"])

    num_topics = st.sidebar.slider("Number of LDA topics", 5, 40, 15)
    run_button = st.sidebar.button("Run analysis ▸")

    return {
        "sample_size": None if sample_size == 0 else sample_size,
        "dr_method": dr_method,
        "dr_params": dr_params,
        "num_topics": num_topics,
        "run": run_button,
        "date_range": date_range,
    }


def main():
    DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
    DATASET_NAME = "News_Category_Dataset_v3"

    st.set_page_config(page_title="High-Dimensional News Visualization", layout="wide")
    st.title("High-Dimensional Text Visualization of HuffPost News")

    cfg = sidebar_configuration()

    if not cfg["run"]:
        st.info("Configure options in the sidebar and press **Run analysis ▸**")
        st.stop()

    # --------------------------- Data loading --------------------------------
    with st.spinner("Loading dataset …"):
        start_date, end_date = pd.to_datetime(cfg["date_range"][0]), pd.to_datetime(cfg["date_range"][1])
        df, idxs = load_dataset(
            f"{DATA_DIR}/{DATASET_NAME}_processed.json",
            start_date,
            end_date,
            count=cfg["sample_size"],
        )

    st.success(f"Loaded {len(df):,} articles.")

    # ------------------------- Embedding loading ---------------------------
    with st.spinner("Loading precomputed BERT embeddings …"):
        X = load_embeddings(f"{DATA_DIR}/{DATASET_NAME}_bert_embeddings.npy", idxs)
    st.success("Loaded BERT embeddings.")

    # ------------------------- Topic modelling ----------------------
    with st.spinner("Running LDA topic model …"):
        tokenized = df["processed_headline"] + df["processed_short_description"]
        doc_topics, lda_model = lda_topics(tokenized, cfg["num_topics"])

    df["topic"] = doc_topics

    with st.expander("Show topic keywords"):
        for t in range(cfg["num_topics"]):
            words = lda_model.show_topic(t, topn=10)
            st.markdown(f"**Topic {t}:** " + ", ".join(w for w, _ in words))

    # ------------------- Dimensionality reduction ----------------------------
    with st.spinner("Reducing dimensions for visualization …"):
        coords = reduce_dimensions(X, cfg["dr_method"], cfg["dr_params"])

    df["x"], df["y"] = coords[:, 0], coords[:, 1]

    st.header("2D Projection of Articles")
    scatter_plots(df)

    st.header("Topic Evolution Over Time")
    topic_evolution_chart(df)

    # ------------------- 3D Plotly Visualization ----------------------------
    with st.spinner("Reducing dimensions for 3D plot …"):
        coords_3d = reduce_dimensions(X, cfg["dr_method"], cfg["dr_params"], n_components=3)

    df["x"], df["y"], df["z"] = coords_3d[:, 0], coords_3d[:, 1], coords_3d[:, 2]

    st.header("3D Projection of Articles")
    plotly_3d_scatter(df)


if __name__ == "__main__":
    main()
