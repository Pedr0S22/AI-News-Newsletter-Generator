import streamlit as st
from client import client

st.set_page_config(
    page_title="AI News Editor Dashboard",
    page_icon="📰",
    layout="wide",
)

# Maintain selected articles in session state for future newsletter synthesis
if "selected_articles" not in st.session_state:
    st.session_state.selected_articles = set()

# Header
st.title("📰 AI News Curation Dashboard")
st.caption("Review recent announcements from primary AI research blogs and curate stories for the newsletter.")

# 1. Action Toolbar
col_fetch, col_refresh, col_metrics = st.columns([0.22, 0.18, 0.6])

with col_fetch:
    if st.button("🚀 Fetch Latest News", type="primary", use_container_width=True):
        with st.spinner("Crawling configured sources for new articles..."):
            success, result, err = client.trigger_ingestion()
            if success and result:
                new_count = result.get("ingested_count", 0)
                st.toast(f"Ingestion complete: {new_count} new articles added!", icon="🎉")
                st.rerun()
            else:
                st.error(f"Ingestion failed: {err}")

with col_refresh:
    if st.button("🔄 Refresh Feed", use_container_width=True):
        st.rerun()

# Fetch latest articles
articles = client.get_articles(limit=100)

with col_metrics:
    selected_count = len(st.session_state.selected_articles)
    st.markdown(
        f"**Stories in Feed:** `{len(articles)}` &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"**Selected for Newsletter:** `{selected_count}`"
    )

st.divider()

# 2. Search & Source Filter Bar
col_search, col_filter = st.columns([0.65, 0.35])

with col_search:
    search_term = st.text_input(
        "Search headlines",
        placeholder="🔍 Type keywords (e.g. Claude, Gemini, reasoning, robotics)...",
        label_visibility="collapsed",
    )

with col_filter:
    all_sources = sorted(list({a.get("source") for a in articles if a.get("source")}))
    selected_source = st.selectbox(
        "Source Filter",
        ["All Sources"] + all_sources,
        label_visibility="collapsed",
    )

# Apply filters
filtered_articles = []
for a in articles:
    # Source filter
    if selected_source != "All Sources" and a.get("source") != selected_source:
        continue

    # Keyword filter
    if search_term:
        term = search_term.lower()
        title_match = term in a.get("title", "").lower()
        summary_match = term in (a.get("summary") or "").lower()
        if not (title_match or summary_match):
            continue

    filtered_articles.append(a)

st.write(f"Showing **{len(filtered_articles)}** of **{len(articles)}** articles")

# 3. Editorial Article Cards
if not filtered_articles:
    st.info("No articles match your criteria. Click **'Fetch Latest News'** or adjust your filters.")
else:
    for art in filtered_articles:
        art_id = str(art.get("id"))
        title = art.get("title") or "Untitled Story"
        source_name = art.get("source") or "Unknown"
        author = art.get("author") or source_name
        published_date = str(art.get("published_at"))[:10]
        summary = art.get("summary")
        canonical_url = art.get("canonical_url", "#")

        with st.container(border=True):
            # Header line: Source badge, date, author
            st.markdown(
                f"🏷️ **{source_name}** &nbsp;•&nbsp; 📅 `{published_date}` &nbsp;•&nbsp; ✍️ *{author}*"
            )

            # Headline
            st.subheader(title)

            # Summary snippet
            if summary:
                st.write(summary)
            else:
                st.caption("*No summary provided by source.*")

            # Action bar: Original link & Newsletter selection
            col_link, col_select = st.columns([0.7, 0.3])
            with col_link:
                st.link_button("Read Original Article ↗", canonical_url)
            with col_select:
                is_selected = st.checkbox(
                    "Select for Newsletter",
                    value=(art_id in st.session_state.selected_articles),
                    key=f"check_{art_id}",
                )
                if is_selected:
                    st.session_state.selected_articles.add(art_id)
                else:
                    st.session_state.selected_articles.discard(art_id)
