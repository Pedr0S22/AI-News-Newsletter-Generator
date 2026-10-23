import streamlit as st
from client import client

st.set_page_config(
    page_title="AI News - Ingestion Dashboard",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 AI News Generator — Dashboard & Ingestion")
st.caption(f"Connected to Backend API: `{client.base_url}`")

# 1. Healthcheck Status
is_healthy, payload, err = client.check_health()
if is_healthy and payload:
    st.success("Backend API is online and healthy", icon="🟢")
else:
    st.error(f"Cannot reach Backend API at `{client.base_url}`: {err}", icon="🔴")

st.divider()

# 2. Ingestion Trigger Section
col_btn, col_info = st.columns([0.3, 0.7])

with col_btn:
    trigger_clicked = st.button("🚀 Run Crawl4AI Ingestion", type="primary")

with col_info:
    st.info(
        "Crawls configured seed sources (OpenAI, Anthropic, DeepMind), performs in-memory "
        "URL deduplication against PostgreSQL, filters by publication date, and saves clean Markdown."
    )

if trigger_clicked:
    with st.spinner("Crawl4AI pipeline executing (discovering links, deduplicating, scraping content)..."):
        success, result, error = client.trigger_ingestion()
        if success and result:
            st.success("Ingestion pipeline completed successfully!")
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Scanned Links", result.get("scanned_links", 0))
            m2.metric("Skipped (Already in DB)", result.get("skipped_existing_urls", 0))
            m3.metric("Skipped (No Date)", result.get("skipped_missing_date", 0))
            m4.metric("Skipped (Too Old)", result.get("skipped_too_old", 0))
            m5.metric("Newly Ingested", result.get("ingested_count", 0))
        else:
            st.error(f"Ingestion pipeline failed: {error}")

st.divider()

# 3. Ingested Articles Feed
st.subheader("📚 Ingested Articles (PostgreSQL Database)")

articles = client.get_articles(limit=50)

if not articles:
    st.write("No articles ingested yet. Click **'Run Crawl4AI Ingestion'** above to fetch articles.")
else:
    st.write(f"Displaying **{len(articles)}** articles stored in PostgreSQL:")
    for art in articles:
        with st.container(border=True):
            col_title, col_meta = st.columns([0.7, 0.3])
            with col_title:
                st.markdown(f"### [{art.get('title')}]({art.get('canonical_url')})")
                st.caption(
                    f"**Source:** {art.get('source')} | "
                    f"**Published:** {str(art.get('published_at'))[:10]} | "
                    f"**Author:** {art.get('author') or 'Unknown'}"
                )
            with col_meta:
                st.caption(f"**UUID:** `{art.get('id')}`")
                st.caption(f"**Ingested:** {str(art.get('created_at'))[:19]}")

            if art.get("summary"):
                st.write(art["summary"])

            with st.expander("📄 View Extracted Markdown Content"):
                st.markdown(art.get("article", "*No content*")[:3000] + ("..." if len(art.get("article", "")) > 3000 else ""))
