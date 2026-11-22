from typing import Any
import streamlit as st
import streamlit.components.v1 as components

from client import MAILPIT_UI_URL, client


def render_newsletter_view(newsletter: dict[str, Any]):
    """Renders an admin-friendly Newsletter Studio: Reader Preview, Inline Editor, and Mailpit Delivery."""
    nl_id = str(newsletter["id"])
    status = str(newsletter.get("status", "draft")).upper()
    structured = newsletter.get("structured_content") or {}

    status_colors = {
        "DRAFT": ("#fefce8", "#854d0e", "Draft — Ready for Editorial Review"),
        "APPROVED": ("#eff6ff", "#1d4ed8", "Approved — Ready to Send"),
        "SENT": ("#ecfdf5", "#065f46", "Sent to Subscribers"),
    }
    bg, fg, label = status_colors.get(status, ("#f1f5f9", "#334155", status))

    st.markdown(
        f"<div style='display:inline-block;background:{bg};color:{fg};padding:5px 14px;"
        f"border-radius:999px;font-size:13px;font-weight:700;margin-bottom:12px;'>"
        f"{label}</div>",
        unsafe_allow_html=True,
    )

    view_preview, view_edit = st.tabs(["👁️ Reader Preview", "✏️ Edit Draft"])

    # ------------------------------------------------------------------
    # Sub-tab 1: Rendered HTML Email Preview (Zero internal scores!)
    # ------------------------------------------------------------------
    with view_preview:
        st.caption(
            "Exact email layout subscribers will receive. All internal AI scores are stripped."
        )
        full_html = newsletter.get("full_html") or ""
        components.html(full_html, height=760, scrolling=True)

        act_c1, act_c2, act_c3 = st.columns([0.34, 0.33, 0.33])
        with act_c1:
            if status == "DRAFT":
                if st.button(
                    "✅ Approve Edition",
                    type="primary",
                    key=f"btn_approve_preview_{nl_id}",
                    use_container_width=True,
                ):
                    ok, _, err = client.approve_newsletter(nl_id)
                    if ok:
                        st.toast("Edition approved! Source trust and metrics updated.", icon="✅")
                        st.rerun()
                    else:
                        st.error(f"Could not approve edition: {err}")
        with act_c2:
            st.download_button(
                "⬇️ Download HTML",
                data=full_html,
                file_name=f"newsletter_{str(newsletter.get('created_at', ''))[:10]}.html",
                mime="text/html",
                use_container_width=True,
            )
        with act_c3:
            st.download_button(
                "⬇️ Download Markdown",
                data=newsletter.get("full_markdown") or "",
                file_name=f"newsletter_{str(newsletter.get('created_at', ''))[:10]}.md",
                mime="text/markdown",
                use_container_width=True,
            )

    # ------------------------------------------------------------------
    # Sub-tab 2: Structured JSON Inline Editor (Save Changes vs Approve)
    # ------------------------------------------------------------------
    with view_edit:
        st.caption(
            "Edit any section below and click **Save Changes** (or press Enter / Ctrl+Enter). "
            "Saving edits will NOT approve the edition until you explicitly click **Approve Edition**."
        )

        with st.form(key=f"edit_newsletter_form_{nl_id}"):
            edition_title = st.text_input(
                "Newsletter Masthead",
                value=structured.get("edition_title") or newsletter.get("edition_title") or "AI Pulse Digest",
            )
            subject = st.text_input(
                "Email Subject Line",
                value=structured.get("subject") or newsletter.get("subject") or "",
            )
            intro = st.text_area(
                "Opening Introduction",
                value=structured.get("intro") or "",
                height=100,
            )

            st.markdown("#### Featured Stories")
            updated_blurbs: list[dict[str, Any]] = []
            for idx, blurb in enumerate(structured.get("blurbs") or []):
                st.markdown(f"**Story #{idx + 1}** — *{blurb.get('source_name', '')}*")
                b_headline = st.text_input(
                    f"Headline #{idx + 1}",
                    value=blurb.get("headline") or "",
                    key=f"hl_{nl_id}_{idx}",
                )
                b_theme = st.text_input(
                    f"Topic Tag #{idx + 1}",
                    value=blurb.get("theme") or "AI News",
                    key=f"th_{nl_id}_{idx}",
                )
                b_body = st.text_area(
                    f"Story Copy #{idx + 1}",
                    value=blurb.get("body") or "",
                    height=150,
                    key=f"bd_{nl_id}_{idx}",
                )
                updated_blurbs.append(
                    {
                        "article_id": blurb.get("article_id", ""),
                        "rank_order": idx + 1,
                        "theme": b_theme,
                        "headline": b_headline,
                        "body": b_body,
                        "source_name": blurb.get("source_name", ""),
                        "source_url": blurb.get("source_url", ""),
                    }
                )
                st.divider()

            outro = st.text_area(
                "Closing Sign-Off",
                value=structured.get("outro") or "",
                height=80,
            )

            # Form submit (and Enter / Ctrl+Enter) ONLY saves edits—never approves!
            saved = st.form_submit_button(
                "💾 Save Changes", use_container_width=True
            )
            if saved:
                payload = {
                    "edition_title": edition_title,
                    "subject": subject,
                    "intro": intro,
                    "blurbs": updated_blurbs,
                    "outro": outro,
                }
                ok, _, err = client.save_newsletter_draft(nl_id, payload)
                if ok:
                    st.toast("Changes saved! Review the preview or click Approve Edition when ready.", icon="💾")
                    st.rerun()
                else:
                    st.error(f"Could not save changes: {err}")

        # Explicit standalone approval button OUTSIDE the form
        st.markdown("")
        if status == "DRAFT":
            if st.button(
                "✅ Approve Edition",
                type="primary",
                key=f"btn_approve_edit_{nl_id}",
                use_container_width=True,
            ):
                ok, _, err = client.approve_newsletter(nl_id)
                if ok:
                    st.toast("Edition approved! Source trust and editorial metrics updated.", icon="✅")
                    st.rerun()
                else:
                    st.error(f"Could not approve edition: {err}")
        elif status == "APPROVED":
            st.success("This edition is already approved and ready to send below.")
        else:
            st.info("This edition has already been sent to subscribers.")

    st.divider()

    # ------------------------------------------------------------------
    # Email Delivery & Subscribers Management (Mailpit)
    # ------------------------------------------------------------------
    st.subheader("📨 Email Delivery & Subscribers")
    col_send, col_subs = st.columns([0.52, 0.48])

    with col_send:
        with st.container(border=True):
            st.markdown("**Send Test Preview**")
            test_email = st.text_input(
                "Test recipient email",
                placeholder="editor@example.com",
                label_visibility="collapsed",
                key=f"test_email_{nl_id}",
            )
            if st.button("Send Test Email", key=f"btn_test_{nl_id}", use_container_width=True):
                if not test_email.strip():
                    st.warning("Enter an email address first.")
                else:
                    ok, res, err = client.send_newsletter(nl_id, test_email=test_email.strip())
                    if ok:
                        st.success(f"Test email delivered to {test_email.strip()}!")
                    else:
                        st.error(f"Failed to send test email: {err}")

            st.markdown("---")
            st.markdown("**Publish & Send to All Active Subscribers**")
            send_disabled = status == "DRAFT"
            if send_disabled:
                st.caption("Approve the edition above before sending to all subscribers.")
            if st.button(
                "📨 Send Newsletter Now",
                type="primary",
                disabled=send_disabled,
                key=f"btn_send_{nl_id}",
                use_container_width=True,
            ):
                ok, res, err = client.send_newsletter(nl_id)
                if ok and res:
                    st.toast(
                        f"Newsletter sent to {res.get('recipients_count', 0)} subscriber(s)!",
                        icon="🎉",
                    )
                    st.rerun()
                else:
                    st.error(f"Failed to send newsletter: {err}")

            st.link_button(
                "📬 Open Mailpit Test Inbox ↗",
                MAILPIT_UI_URL,
                use_container_width=True,
            )

    with col_subs:
        with st.container(border=True):
            st.markdown("**Subscriber List**")
            sub_email = st.text_input(
                "Add subscriber email",
                placeholder="reader@university.pt",
                key=f"new_sub_email_{nl_id}",
            )
            sub_name = st.text_input(
                "Name (optional)",
                placeholder="Reader Name",
                key=f"new_sub_name_{nl_id}",
            )
            if st.button("➕ Add Subscriber", key=f"btn_add_sub_{nl_id}", use_container_width=True):
                if not sub_email.strip():
                    st.warning("Please enter an email address.")
                else:
                    ok, _, err = client.add_subscriber(sub_email.strip(), sub_name.strip() or None)
                    if ok:
                        st.toast(f"Added {sub_email.strip()}", icon="📬")
                        st.rerun()
                    else:
                        st.error(f"Could not add subscriber: {err}")

            subscribers = client.list_subscribers()
            if not subscribers:
                st.caption("No subscribers yet. Add an email above to test full delivery.")
            else:
                st.markdown(f"**Active Subscribers ({len(subscribers)})**")
                for sub in subscribers:
                    sc1, sc2 = st.columns([0.8, 0.2])
                    display_label = (
                        f"{sub['name']} ({sub['email']})" if sub.get("name") else sub["email"]
                    )
                    with sc1:
                        st.write(f"• {display_label}")
                    with sc2:
                        if st.button("🗑️", key=f"del_sub_{nl_id}_{sub['id']}", help="Remove"):
                            client.remove_subscriber(str(sub["id"]))
                            st.rerun()
