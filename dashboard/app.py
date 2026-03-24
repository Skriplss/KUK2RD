import streamlit as st
import asyncio
import pandas as pd
import requests
import json
import time

from sqlalchemy import select, func
from src.core.database import init_db, AsyncSessionLocal, KnowledgeObject, engine
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ── Category color palette ─────────────────────────────────────────────────
CATEGORY_COLORS: dict[str, str] = {
    "RawMaterial":  "#2196F3",   # blue
    "Process":      "#FF9800",   # orange
    "Manufacturer": "#9C27B0",   # purple
    "Product":      "#4CAF50",   # green
    "Intermediate": "#00BCD4",   # cyan
    "Equipment":    "#F44336",   # red
    "Unknown":      "#9E9E9E",   # grey
}

def category_badge(category: str) -> str:
    color = CATEGORY_COLORS.get(category, "#9E9E9E")
    return (
        f'<span style="background:{color};color:white;padding:2px 10px;'
        f'border-radius:12px;font-size:0.78em;font-weight:600;">{category}</span>'
    )

# ── Helpers ────────────────────────────────────────────────────────────────
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()

def safe_dict(val) -> dict:
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            result = json.loads(val)
            return result if isinstance(result, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}

# ── DB helpers ─────────────────────────────────────────────────────────────
@st.cache_resource
def setup_db():
    if "db_initialized" not in st.session_state:
        run_async(init_db())
        st.session_state.db_initialized = True

async def get_objects_by_status(status: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(KnowledgeObject)
            .filter(KnowledgeObject.status == status)
            .order_by(KnowledgeObject.id.desc())
        )
        return result.scalars().all()

async def get_counts():
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(KnowledgeObject.status, func.count().label("cnt"))
            .group_by(KnowledgeObject.status)
        )
        return {r.status: r.cnt for r in rows}

async def update_object_status(obj_id: int, new_status: str, new_data: dict = None):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(KnowledgeObject).filter(KnowledgeObject.id == obj_id)
        )
        obj = result.scalar_one_or_none()
        if obj:
            obj.status = new_status
            if new_data is not None:
                obj.data = new_data
            await session.commit()

# ── Page setup ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="KUK2RD Dashboard", layout="wide")
setup_db()

st.title("KUK2RD — Curator Dashboard")
st.caption("Systém extrakcie znalostí z technických dokumentov gumárenskej chémie")
st.divider()

# ── Global metric cards ────────────────────────────────────────────────────
counts = run_async(get_counts())
total    = sum(counts.values())
pending  = counts.get("PENDING", 0)
approved = counts.get("APPROVED", 0)
rejected = counts.get("REJECTED", 0)

m1, m2, m3, m4 = st.columns(4)
m1.metric("📦 Celkom objektov", total)
m2.metric("🟡 Čaká na schválenie", pending, delta=None)
m3.metric("✅ Schválených", approved)
m4.metric("❌ Zamietnutých", rejected)
st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────
tab_upload, tab_review, tab_database = st.tabs([
    "📤 Nahrať dokument",
    "🔍 Prehľad (Kurátor)",
    "🗄️ Znalostná databáza (CORE DATA)"
])

# ══════════════════════════════════════════════════════════════════════════
# TAB 1 — Upload
# ══════════════════════════════════════════════════════════════════════════
with tab_upload:
    st.write("Nahrajte PDF alebo DOCX súbory. Systém ich postupne spracuje a extrahuje znalostné objekty.")

    uploaded_files = st.file_uploader(
        "Vyberte jeden alebo viac dokumentov",
        type=["pdf", "docx"],
        accept_multiple_files=True
    )

    if uploaded_files:
        st.info(f"Vybrané súbory: **{len(uploaded_files)}**")

        # ── OCR Preview ────────────────────────────────────────────────
        with st.expander("👁️ Predprosessor — náhľad OCR textu (voliteľné)", expanded=False):
            preview_file = st.selectbox(
                "Vyberte súbor na náhľad:",
                options=[f.name for f in uploaded_files],
                key="preview_select"
            )
            if st.button("Zobraziť rozpoznaný text (OCR Preview)", key="btn_preview"):
                target = next(f for f in uploaded_files if f.name == preview_file)
                with st.spinner("Spúšťam OCR parser..."):
                    try:
                        resp = requests.post(
                            "http://api:8000/preview",
                            files={"file": (target.name, target.getvalue(), "application/octet-stream")}
                        )
                        if resp.status_code == 200:
                            pdata = resp.json()
                            st.success(f"Rozpoznaných segmentov: **{pdata['chunks_count']}**")
                            for i, chunk in enumerate(pdata["chunks"]):
                                st.text_area(
                                    f"Segment {i+1}",
                                    value=chunk,
                                    height=200,
                                    key=f"chunk_prev_{i}",
                                    disabled=True
                                )
                        else:
                            st.error(f"Chyba API: {resp.text}")
                    except Exception as e:
                        st.error(f"Chyba: {e}")

        st.write("---")

        # ── Batch extraction ────────────────────────────────────────────
        if st.button("🚀 Spustiť AI extrakciu pre všetky súbory", type="primary"):
            overall_bar   = st.progress(0, text="Inicializácia...")
            results_table = []

            for file_idx, ufile in enumerate(uploaded_files):
                fname = ufile.name
                step_pct = int((file_idx / len(uploaded_files)) * 100)
                overall_bar.progress(step_pct, text=f"Spracovávam {file_idx+1}/{len(uploaded_files)}: **{fname}**")

                file_status = st.empty()
                file_status.info(f"⏳ `{fname}` — odosielanie na API...")

                try:
                    resp = requests.post(
                        "http://api:8000/upload",
                        files={"file": (fname, ufile.getvalue(), "application/octet-stream")}
                    )
                    if resp.status_code == 200:
                        d = resp.json()
                        file_status.success(
                            f"✅ `{fname}` — "
                            f"{d['chunks_processed']} segmentov → **{d['objects_extracted']} nových objektov**"
                        )
                        results_table.append({
                            "Súbor": fname,
                            "Segmenty": d["chunks_processed"],
                            "Nové objekty": d["objects_extracted"],
                            "Stav": "✅ OK"
                        })
                    else:
                        file_status.error(f"❌ `{fname}` — Chyba: {resp.text[:120]}")
                        results_table.append({"Súbor": fname, "Segmenty": "-", "Nové objekty": "-", "Stav": "❌ Chyba"})
                except Exception as e:
                    file_status.error(f"❌ `{fname}` — {e}")
                    results_table.append({"Súbor": fname, "Segmenty": "-", "Nové objekty": "-", "Stav": "❌ Výnimka"})

            overall_bar.progress(100, text="Všetky súbory spracované!")
            st.write("### Súhrn dávky")
            st.dataframe(pd.DataFrame(results_table), use_container_width=True, hide_index=True)
            st.info("Prejdite na kartu 'Prehľad (Kurátor)' pre kontrolu nových návrhov.")


# ══════════════════════════════════════════════════════════════════════════
# TAB 2 — Curator Review
# ══════════════════════════════════════════════════════════════════════════
with tab_review:
    st.write("Návrhy znalostných objektov od AI — ešte nie sú autoritatívne schválené.")

    pending_objs = run_async(get_objects_by_status("PENDING"))

    if not pending_objs:
        st.success("Aktuálne nie sú na schválenie žiadne nové objekty.")
    else:
        st.info(f"Na vaše schválenie čaká **{len(pending_objs)}** objektov.")

        pending_cats = sorted({obj.category for obj in pending_objs})
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            p_search = st.text_input("Vyhľadávanie (text):", key="p_search")
        with col_f2:
            p_cats = st.multiselect("Filter kategórie:", options=pending_cats, key="p_cats")

        st.write("---")

        for obj in pending_objs:
            if p_search and p_search.lower() not in str(obj.data).lower():
                continue
            if p_cats and obj.category not in p_cats:
                continue

            data_dict  = safe_dict(obj.data)
            metadata   = safe_dict(data_dict.get("metadata", {}))
            source     = metadata.get("source_file", "Neznámy súbor")
            chunk_idx  = metadata.get("source_chunk_idx", "N/A")
            source_txt = metadata.get("source_text", "Textový kontext nebol uložený.")
            name_en    = data_dict.get("name_en", f"ID {obj.id}")

            # Colored category badge in expander header
            header_html = f"{name_en} &nbsp; {category_badge(obj.category)}"
            with st.expander(f"ID {obj.id} — {name_en} [{obj.category}]", expanded=False):
                st.markdown(header_html, unsafe_allow_html=True)
                st.caption(f"Zdrojový súbor: **{source}** · Segment #{chunk_idx}")

                s1, s2 = st.columns([1.2, 1])
                with s1:
                    st.write("**Parametre (možnosť editácie):**")
                    edited_df = st.data_editor(
                        pd.DataFrame([data_dict]),
                        key=f"editor_{obj.id}",
                        use_container_width=True,
                    )
                    edited_data = edited_df.to_dict("records")[0]

                with s2:
                    st.write(f"**Pôvodný text z `{source}`:**")
                    st.info(source_txt, icon="📄")

                st.write("---")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ Schváliť (Approve)", key=f"approve_{obj.id}", type="primary", use_container_width=True):
                        run_async(update_object_status(obj.id, "APPROVED", edited_data))
                        st.toast("Objekt autorizovaný do CORE DATA!", icon="🏆")
                        st.rerun()
                with c2:
                    if st.button("❌ Zamietnuť", key=f"reject_{obj.id}", use_container_width=True):
                        run_async(update_object_status(obj.id, "REJECTED"))
                        st.toast("Objekt zamietnutý.", icon="🗑️")
                        st.rerun()

# ══════════════════════════════════════════════════════════════════════════
# TAB 3 — CORE DATA
# ══════════════════════════════════════════════════════════════════════════
with tab_database:
    st.write("Finálne schválené objekty — **CORE DATA** autoritatívnej vrstvy znalostí.")

    approved_objs = run_async(get_objects_by_status("APPROVED"))

    if not approved_objs:
        st.info("Zatiaľ neboli schválené žiadne objekty.")
    else:
        categories = [obj.category for obj in approved_objs]
        cat_counts = pd.Series(categories).value_counts().reset_index()
        cat_counts.columns = ["Kategória", "Počet"]

        # Metric cards per category
        unique_cats = cat_counts["Kategória"].tolist()
        cols = st.columns(min(len(unique_cats), 6))
        for i, cat in enumerate(unique_cats):
            color = CATEGORY_COLORS.get(cat, "#9E9E9E")
            cnt = cat_counts.loc[cat_counts["Kategória"] == cat, "Počet"].values[0]
            cols[i].markdown(
                f'<div style="background:{color}22;border-left:4px solid {color};'
                f'padding:8px 12px;border-radius:6px;margin-bottom:4px">'
                f'<strong style="color:{color}">{cat}</strong><br>'
                f'<span style="font-size:1.4em;font-weight:700">{cnt}</span></div>',
                unsafe_allow_html=True
            )

        st.write("")
        col1, col2 = st.columns([1, 4])
        with col1:
            export_data = [safe_dict(obj.data) for obj in approved_objs]
            st.download_button(
                label="⬇️ Export JSON",
                data=json.dumps(export_data, ensure_ascii=False, indent=2),
                file_name="core_data_export.json",
                mime="application/json",
                use_container_width=True
            )

        with col2:
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                db_search = st.text_input("Hľadať:", key="db_search")
            with f_col2:
                db_cats = st.multiselect("Kategórie:", options=sorted(set(categories)), key="db_cats")

            flat_data = []
            for obj in approved_objs:
                data_dict = safe_dict(obj.data)
                metadata  = safe_dict(data_dict.get("metadata", {}))
                cat = obj.category
                color = CATEGORY_COLORS.get(cat, "#9E9E9E")
                row = {
                    "ID": obj.id,
                    "Kategória": cat,
                    "Originálny názov": data_dict.get("original_name", ""),
                    "Názov (EN)": data_dict.get("name_en", ""),
                    "Popis": data_dict.get("description", ""),
                    "Zdroj": metadata.get("source_file", ""),
                }
                if db_cats and row["Kategória"] not in db_cats:
                    continue
                if db_search:
                    row_text = " ".join(str(v) for v in row.values()).lower()
                    if db_search.lower() not in row_text:
                        continue
                flat_data.append(row)

            if flat_data:
                st.dataframe(pd.DataFrame(flat_data), use_container_width=True, hide_index=True)
            else:
                st.warning("Žiadne dáta nezodpovedajú filtru.")
