from typing import Any, Callable, Optional
import streamlit as st


def _truncate(text: Optional[str], limit: int = 350) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rsplit(" ", 1)[0] + "..."


def _score_tags_html(article: dict[str, Any]) -> str:
    """Renders clean, admin-friendly pill tags for internal evaluation metrics."""
    tags: list[str] = []

    theme = article.get("primary_theme")
    if theme:
        tags.append(
            f"<span style='background:#eef2ff;color:#3730a3;padding:3px 10px;"
            f"border-radius:999px;font-size:12px;font-weight:600;margin-right:6px;'>"
            f"{theme}</span>"
        )

    final_score = article.get("final_ranking_score")
    if final_score is not None and final_score > 0:
        tags.append(
            f"<span style='background:#ecfdf5;color:#065f46;padding:3px 10px;"
            f"border-radius:999px;font-size:12px;font-weight:700;margin-right:6px;'>"
            f"Overall: {final_score:.2f}</span>"
        )

    fact = article.get("factuality_score")
    if fact is not None:
        tags.append(
            f"<span style='background:#eff6ff;color:#1d4ed8;padding:3px 10px;"
            f"border-radius:999px;font-size:12px;font-weight:600;margin-right:6px;'>"
            f"Factuality: {fact:.1f}/10</span>"
        )

    hype = article.get("hype_score")
    if hype is not None:
        hype_bg = "#f0fdf4" if hype <= 3.5 else ("#fefce8" if hype <= 6.5 else "#fef2f2")
        hype_fg = "#166534" if hype <= 3.5 else ("#854d0e" if hype <= 6.5 else "#991b1b")
        tags.append(
            f"<span style='background:{hype_bg};color:{hype_fg};padding:3px 10px;"
            f"border-radius:999px;font-size:12px;font-weight:600;margin-right:6px;'>"
            f"Hype: {hype:.1f}/10 (lower is better)</span>"
        )

    rep = article.get("reputation_multiplier")
    if rep is not None:
        tags.append(
            f"<span style='background:#f8fafc;color:#475569;border:1px solid #cbd5e1;"
            f"padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;'>"
            f"Source Trust: {rep:.2f}x</span>"
        )

    return "".join(tags)


def render_article_card(
    article: dict[str, Any],
    *,
    mode: str = "shortlist",
    rank_position: Optional[int] = None,
    total_in_shortlist: int = 0,
    can_add_more: bool = True,
    on_move_up: Optional[Callable[[], None]] = None,
    on_move_down: Optional[Callable[[], None]] = None,
    on_reject: Optional[Callable[[], None]] = None,
    on_add: Optional[Callable[[], None]] = None,
    key_prefix: str = "card",
):
    """Renders a clean Admin editorial card with score badges and explainability."""
    art_id = str(article.get("article_id", ""))
    title = article.get("title") or "Untitled Story"
    source_name = article.get("source") or "Unknown"
    author = article.get("author") or source_name
    published_date = str(article.get("published_at") or "")[:10]
    summary = _truncate(article.get("summary"), 350)
    article_url = article.get("canonical_url") or article.get("original_url") or "#"

    with st.container(border=True):
        # Metadata header
        rank_label = f"**#{rank_position}** &nbsp;•&nbsp; " if rank_position else ""
        st.markdown(
            f"{rank_label}🏷️ **{source_name}** &nbsp;•&nbsp; 📅 `{published_date}` &nbsp;•&nbsp; ✍️ *{author}*"
        )

        # Metric pill tags (visible only to Admin during curation, NEVER in newsletter!)
        tags_html = _score_tags_html(article)
        if tags_html:
            st.markdown(f"<div style='margin:6px 0 8px 0;'>{tags_html}</div>", unsafe_allow_html=True)

        # Headline & Summary
        st.subheader(title)
        if summary:
            st.write(summary)
        else:
            st.caption("*No summary provided by source.*")

        # Plain-English Explainability Drawer
        with st.expander("Why did our editors score it this way?"):
            if article.get("topic_reason"):
                st.markdown(f"**Topic Check:** {article['topic_reason']}")
            if article.get("factuality_reason"):
                st.markdown(f"**Factuality Check:** {article['factuality_reason']}")
            if article.get("hype_reason"):
                st.markdown(f"**Hype Assessment:** {article['hype_reason']}")
            if article.get("dedup_reason"):
                st.markdown(f"**Uniqueness Check:** {article['dedup_reason']}")

            sources = article.get("verification_sources") or []
            if sources:
                st.markdown("**Corroborating References Checked:**")
                for ref in sources:
                    origin_label = "Web" if ref.get("origin") == "web" else "Archive"
                    ref_title = ref.get("title") or ref.get("url")
                    st.markdown(f"- [{ref_title}]({ref.get('url')}) *({origin_label})*")

        # Action Toolbar
        if mode == "shortlist":
            c_read, c_up, c_down, c_rej = st.columns([0.46, 0.16, 0.16, 0.22])
            with c_read:
                st.link_button("Read Original Article ↗", article_url)
            with c_up:
                if st.button(
                    "⬆️ Move Up",
                    key=f"{key_prefix}_up_{art_id}",
                    disabled=(rank_position == 1),
                    use_container_width=True,
                ):
                    if on_move_up:
                        on_move_up()
            with c_down:
                if st.button(
                    "⬇️ Move Down",
                    key=f"{key_prefix}_down_{art_id}",
                    disabled=(rank_position == total_in_shortlist),
                    use_container_width=True,
                ):
                    if on_move_down:
                        on_move_down()
            with c_rej:
                if st.button(
                    "✖ Reject",
                    key=f"{key_prefix}_rej_{art_id}",
                    use_container_width=True,
                ):
                    if on_reject:
                        on_reject()
        elif mode == "pool":
            c_read, c_add = st.columns([0.7, 0.3])
            with c_read:
                st.link_button("Read Original Article ↗", article_url)
            with c_add:
                if st.button(
                    "➕ Add to Edition",
                    key=f"{key_prefix}_add_{art_id}",
                    disabled=not can_add_more,
                    use_container_width=True,
                ):
                    if on_add:
                        on_add()
        else:
            # Eliminated / Filtered view
            status_label = (
                "Off-Topic" if article.get("status") == "eliminated_topic" else "Duplicate Story"
            )
            c_read, c_badge = st.columns([0.7, 0.3])
            with c_read:
                st.link_button("Read Original Article ↗", article_url)
            with c_badge:
                st.caption(f"Filtered out: **{status_label}**")
