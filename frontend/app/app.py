import pandas as pd
import streamlit as st

from client import client
from components.article_card import render_article_card
from components.newsletter_view import render_newsletter_view

st.set_page_config(
    page_title="AI Pulse — Editorial Dashboard",
    page_icon="📰",
    layout="wide",
)

# Session state for interactive Human-in-the-Loop curation
if "curated_ids" not in st.session_state:
    st.session_state.curated_ids = None
if "rejected_ids" not in st.session_state:
    st.session_state.rejected_ids = []
if "suggested_top_n_ids" not in st.session_state:
    st.session_state.suggested_top_n_ids = []
if "last_top_n" not in st.session_state:
    st.session_state.last_top_n = 3
if "active_newsletter_id" not in st.session_state:
    st.session_state.active_newsletter_id = None

# Header
st.title("📰 AI Pulse — Editorial Dashboard")
st.caption(
    "Automated AI news discovery, multi-agent quality scoring, human-in-the-loop curation, and newsletter delivery."
)

tab_curation, tab_studio, tab_analytics = st.tabs(
    [
        "📰 Editorial Curation",
        "✉️ Newsletter Studio & Delivery",
        "📊 Trust & Quality Analytics",
    ]
)

# ==============================================================================
# TAB 1: EDITORIAL CURATION (Automatic Ingestion + Scoring + HitL Top-N Review)
# ==============================================================================
with tab_curation:
    col_fetch, col_topn, col_refresh = st.columns([0.36, 0.34, 0.30])

    with col_fetch:
        if st.button(
            "🚀 Fetch & Score Latest News", type="primary", use_container_width=True
        ):
            with st.spinner(
                "Crawling sources and running AI quality evaluation (Topic, Factuality, Hype & Uniqueness)..."
            ):
                ok, result, err = client.trigger_ingestion()
                if ok and result:
                    new_ing = result.get("ingested_count", 0)
                    new_eval = result.get("evaluated_count", 0)
                    st.session_state.curated_ids = None
                    st.session_state.rejected_ids = []
                    st.toast(
                        f"Done! {new_ing} new stories fetched, {new_eval} stories evaluated.",
                        icon="🎉",
                    )
                    st.rerun()
                else:
                    st.error(f"Could not fetch latest news: {err}")

    with col_topn:
        top_n = st.selectbox(
            "Stories per Edition",
            options=[1, 2, 3, 4, 5],
            index=2,  # Default = 3 (Recommended)
            format_func=lambda n: f"Top {n} Stories (Recommended)" if n == 3 else f"Top {n} Stories",
            label_visibility="collapsed",
        )

    with col_refresh:
        if st.button("🔄 Refresh Shortlist", use_container_width=True):
            st.session_state.curated_ids = None
            st.session_state.rejected_ids = []
            st.rerun()

    rankings = client.get_rankings(top_n=top_n)

    if rankings is None:
        st.warning("Unable to reach the editorial service right now. Please try refreshing in a moment.")
    else:
        unevaluated_count = rankings.get("unevaluated_count", 0)
        if unevaluated_count > 0:
            ban_c1, ban_c2 = st.columns([0.75, 0.25])
            with ban_c1:
                st.info(
                    f"**{unevaluated_count}** fetched stories are waiting to be scored by the AI editors."
                )
            with ban_c2:
                if st.button("✨ Score Pending Stories", use_container_width=True):
                    with st.spinner("Scoring pending stories with AI editors..."):
                        ok, res, err = client.trigger_evaluation()
                        if ok and res:
                            st.session_state.curated_ids = None
                            st.session_state.rejected_ids = []
                            st.toast(
                                f"Scored {res.get('evaluated_count', 0)} stories!", icon="✅"
                            )
                            st.rerun()
                        else:
                            st.error(f"Scoring failed: {err}")

        recommended = rankings.get("recommended", [])
        candidate_pool = rankings.get("candidate_pool", [])
        eliminated = rankings.get("eliminated", [])

        all_selectable = recommended + candidate_pool
        by_id = {str(a["article_id"]): a for a in all_selectable}

        # Sync initial HitL selection when rankings load or Top-N selector changes
        if (
            st.session_state.curated_ids is None
            or st.session_state.last_top_n != top_n
        ):
            st.session_state.suggested_top_n_ids = [str(a["article_id"]) for a in recommended]
            st.session_state.curated_ids = list(st.session_state.suggested_top_n_ids)
            st.session_state.rejected_ids = []
            st.session_state.last_top_n = top_n

        # Filter out any stale IDs (e.g. after publishing an edition)
        curated_ids = [aid for aid in st.session_state.curated_ids if aid in by_id]
        st.session_state.curated_ids = curated_ids

        # --- Edition Shortlist Section ---
        st.divider()
        st.subheader(f"🏆 Recommended Shortlist ({len(curated_ids)} / 5 max)")
        st.caption(
            "Ranked by Factuality, Low Hype, and Source Trust. Reorder, remove, or swap stories below—your choices train Source Trust automatically."
        )

        if not curated_ids:
            st.info(
                "No stories selected yet. Click **'Fetch & Score Latest News'** or add stories from the candidate pool below."
            )
        else:
            for idx, aid in enumerate(curated_ids):
                art = by_id[aid]

                def _make_move_up(i=idx):
                    ids = list(st.session_state.curated_ids)
                    ids[i - 1], ids[i] = ids[i], ids[i - 1]
                    st.session_state.curated_ids = ids
                    st.rerun()

                def _make_move_down(i=idx):
                    ids = list(st.session_state.curated_ids)
                    ids[i + 1], ids[i] = ids[i], ids[i + 1]
                    st.session_state.curated_ids = ids
                    st.rerun()

                def _make_reject(target_id=aid):
                    st.session_state.curated_ids = [
                        x for x in st.session_state.curated_ids if x != target_id
                    ]
                    if (
                        target_id in st.session_state.suggested_top_n_ids
                        and target_id not in st.session_state.rejected_ids
                    ):
                        st.session_state.rejected_ids.append(target_id)
                    st.rerun()

                render_article_card(
                    art,
                    mode="shortlist",
                    rank_position=idx + 1,
                    total_in_shortlist=len(curated_ids),
                    on_move_up=_make_move_up,
                    on_move_down=_make_move_down,
                    on_reject=_make_reject,
                    key_prefix="shortlist",
                )

            # Confirm Selection & Draft Newsletter Box
            st.markdown("")
            with st.container(border=True):
                dc1, dc2 = st.columns([0.55, 0.45])
                with dc1:
                    edition_title = st.text_input(
                        "Edition Title",
                        value="AI Pulse Digest",
                        help="Masthead title shown at the top of the newsletter.",
                    )
                with dc2:
                    st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
                    if st.button(
                        f"✍️ Confirm Selection & Draft Newsletter ({len(curated_ids)} stories)",
                        type="primary",
                        use_container_width=True,
                    ):
                        with st.spinner(
                            "Drafting journalistic copy and running editorial quality review..."
                        ):
                            ok, draft, err = client.draft_newsletter(
                                selected_article_ids=curated_ids,
                                rejected_article_ids=st.session_state.rejected_ids,
                                suggested_top_n_ids=st.session_state.suggested_top_n_ids,
                                edition_title=edition_title.strip() or "AI Pulse Digest",
                            )
                            if ok and draft:
                                st.session_state.active_newsletter_id = str(draft["id"])
                                st.session_state.rejected_ids = []
                                st.toast(
                                    "Draft ready! Open the 'Newsletter Studio & Delivery' tab to review and send.",
                                    icon="✉️",
                                )
                                st.rerun()
                            else:
                                st.error(f"Could not draft newsletter: {err}")

        # --- Candidate Pool & Search ---
        st.divider()
        st.subheader("📚 More Evaluated Stories")
        remaining_pool = [a for a in all_selectable if str(a["article_id"]) not in curated_ids]

        s_col, f_col = st.columns([0.65, 0.35])
        with s_col:
            search_term = st.text_input(
                "Search stories",
                placeholder="🔍 Search headlines or summaries...",
                label_visibility="collapsed",
            )
        with f_col:
            all_sources = sorted({a.get("source") for a in remaining_pool if a.get("source")})
            selected_source = st.selectbox(
                "Filter by Source",
                ["All Sources"] + all_sources,
                label_visibility="collapsed",
            )

        filtered_pool = []
        for a in remaining_pool:
            if selected_source != "All Sources" and a.get("source") != selected_source:
                continue
            if search_term:
                term = search_term.lower()
                if term not in (a.get("title") or "").lower() and term not in (
                    a.get("summary") or ""
                ).lower():
                    continue
            filtered_pool.append(a)

        if not filtered_pool:
            st.caption("No additional candidate stories match your filter.")
        else:
            can_add_more = len(curated_ids) < 5
            if not can_add_more:
                st.caption("Maximum of 5 stories selected. Reject one above to add another.")
            for art in filtered_pool:
                aid = str(art["article_id"])

                def _make_add(target_id=aid):
                    if len(st.session_state.curated_ids) < 5 and target_id not in st.session_state.curated_ids:
                        st.session_state.curated_ids.append(target_id)
                        st.session_state.rejected_ids = [
                            x for x in st.session_state.rejected_ids if x != target_id
                        ]
                        st.rerun()

                render_article_card(
                    art,
                    mode="pool",
                    can_add_more=can_add_more,
                    on_add=_make_add,
                    key_prefix="pool",
                )

        # --- Eliminated Stories Audit Drawer ---
        if eliminated:
            with st.expander(f"🧹 Filtered Out Stories ({len(eliminated)} off-topic or duplicate)"):
                for art in eliminated:
                    render_article_card(art, mode="eliminated", key_prefix="elim")

# ==============================================================================
# TAB 2: NEWSLETTER STUDIO & DELIVERY
# ==============================================================================
with tab_studio:
    editions = client.list_newsletters()
    if not editions:
        st.info(
            "No newsletter editions yet. Review your shortlist in **Editorial Curation** and click **'Confirm Selection & Draft Newsletter'**."
        )
    else:
        edition_ids = [str(e["id"]) for e in editions]
        labels_by_id = {
            str(e["id"]): (
                f"[{str(e.get('status', 'draft')).upper()}] "
                f"{str(e.get('created_at', ''))[:10]} — {e.get('subject', e.get('edition_title', 'Edition'))}"
            )
            for e in editions
        }

        default_idx = 0
        if st.session_state.active_newsletter_id in edition_ids:
            default_idx = edition_ids.index(st.session_state.active_newsletter_id)

        chosen_id = st.selectbox(
            "Select Newsletter Edition",
            options=edition_ids,
            index=default_idx,
            format_func=lambda eid: labels_by_id.get(eid, "Edition"),
        )
        st.session_state.active_newsletter_id = chosen_id

        newsletter = client.get_newsletter(chosen_id)
        if newsletter:
            render_newsletter_view(newsletter)
        else:
            st.error("Could not load the selected newsletter edition.")

# ==============================================================================
# TAB 3: TRUST & QUALITY ANALYTICS (Proposal Section 5 — Admin View)
# ==============================================================================
with tab_analytics:
    st.subheader("📊 Editorial Autonomy & Source Trust")
    st.caption(
        "Tracks how accurately the AI editors suggest top stories and how human curation shapes each source's trust multiplier."
    )

    analytics = client.get_analytics()
    if not analytics:
        st.info("Analytics will appear once stories have been evaluated.")
    else:
        # KPI Cards
        k1, k2, k3, k4 = st.columns(4)
        retention = analytics.get("avg_top_n_retention_rate")
        unedited = analytics.get("unedited_approval_rate")

        with k1:
            st.metric(
                "Top-N Acceptance Rate",
                f"{retention * 100:.0f}%" if retention is not None else "—",
                help="Share of AI-recommended Top-N stories kept by the human editor.",
            )
        with k2:
            st.metric(
                "Unedited Approval Rate",
                f"{unedited * 100:.0f}%" if unedited is not None else "—",
                help="Share of drafted stories approved without manual copy edits.",
            )
        with k3:
            st.metric(
                "Editions Sent",
                f"{analytics.get('editions_sent', 0)} / {analytics.get('editions_drafted', 0)} drafted",
            )
        with k4:
            st.metric("Active Subscribers", analytics.get("active_subscribers", 0))

        st.divider()

        reputations = analytics.get("reputations") or []
        if not reputations:
            st.info("No source trust records yet. Fetch and score stories to initialize source trust.")
        else:
            st.subheader("🛡️ Source Trust Leaderboard")
            rep_rows = [
                {
                    "Source": r["source_name"],
                    "Trust Multiplier": round(r["reputation_score"], 3),
                    "Evaluated": r["total_evaluated"],
                    "Accepted": r["accepted_count"],
                    "Edited": r["edited_count"],
                    "Promoted": r["promoted_count"],
                    "Rejected": r["rejected_count"],
                }
                for r in reputations
            ]
            rep_df = pd.DataFrame(rep_rows)

            c_chart, c_table = st.columns([0.5, 0.5])
            with c_chart:
                st.bar_chart(rep_df.set_index("Source")[["Trust Multiplier"]])
            with c_table:
                st.dataframe(rep_df, hide_index=True, use_container_width=True)

            # Reputation Evolution History
            history_points = []
            for r in reputations:
                src = r["source_name"]
                for step_idx, entry in enumerate(r.get("history") or []):
                    history_points.append(
                        {
                            "Step": step_idx,
                            "Timestamp": entry.get("timestamp", ""),
                            "Source": src,
                            "Trust Score": entry.get("new_score", 1.0),
                        }
                    )

            if len(history_points) > len(reputations):
                st.subheader("📈 Source Trust Evolution")
                hist_df = pd.DataFrame(history_points)
                pivot = hist_df.pivot_table(
                    index="Step", columns="Source", values="Trust Score", aggfunc="last"
                ).ffill()
                st.line_chart(pivot)
