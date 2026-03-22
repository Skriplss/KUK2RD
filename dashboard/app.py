import streamlit as st
import asyncio
import pandas as pd
import requests
import json

from sqlalchemy import select
from src.core.database import init_db, AsyncSessionLocal, KnowledgeObject, engine
from src.utils.logger import get_logger

logger = get_logger(__name__)

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()

st.set_page_config(page_title="KUK2RD Dashboard", layout="wide")
st.title("KUK2RD - Curator Dashboard")

@st.cache_resource
def setup_db():
    if "db_initialized" not in st.session_state:
        run_async(init_db())
        st.session_state.db_initialized = True

setup_db()

async def get_pending_objects():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(KnowledgeObject).filter(KnowledgeObject.status == "PENDING").order_by(KnowledgeObject.id.desc())
        )
        return result.scalars().all()

async def get_approved_objects():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(KnowledgeObject).filter(KnowledgeObject.status == "APPROVED").order_by(KnowledgeObject.id.desc())
        )
        return result.scalars().all()

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

tab_upload, tab_review, tab_database = st.tabs([
    "Nahrať dokument (Upload API)", 
    "Prehľad a schválenie (Kurátor)",
    "Znalostná databáza (CORE DATA)"
])

with tab_upload:
    st.write("Nahrajte PDF alebo DOCX na extrakciu dát pomocou znalostného systému. Extrakcia prebieha na dedikovanom CORE API.")
    uploaded_file = st.file_uploader("Vyberte dokument", type=["pdf", "docx"])
    
    if uploaded_file is not None and st.button("Spustiť AI extrakciu do CORE DATA", type="primary"):
        with st.spinner("Dokument sa spracováva cez backend API (môže to minútku trvať)..."):
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/octet-stream")}
                # Voláme naše FastAPI z docker networku
                response = requests.post("http://api:8000/upload", files=files)
                
                if response.status_code == 200:
                    data = response.json()
                    st.success(f"**Extrakcia úspešná!** Z {data.get('chunks_processed')} segmentov sa našlo **{data.get('objects_extracted')} objektov**.")
                    st.info("Prejdite na kartu 'Prehľad a schválenie (Kurátor)' pre kontrolu návrhov od umelej inteligencie.")
                else:
                    st.error(f"Chyba na serveri: {response.text}")
            except requests.exceptions.ConnectionError:
                st.error("Nepodarilo sa spojiť s API. Uistite sa, že docker kontajner `api` beží (port 8000).")
            except Exception as e:
                st.error(f"Neočakávaná chyba: {e}")

with tab_review:
    st.write("Návrhy znalostných objektov od AI. Tieto dáta autoritatívne nie sú schválené.")
    
    pending_objs = run_async(get_pending_objects())
    
    if not pending_objs:
        st.success("Aktuálne nie sú na schválenie žiadne nové objekty.")
    else:
        st.info(f"Na vaše schválenie čaká {len(pending_objs)} objektov.")
        
        pending_cats = sorted(list(set([obj.category for obj in pending_objs])))
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            p_search = st.text_input("Vyhľadávanie v návrhoch (text):", key="p_search")
        with col_f2:
            p_cats = st.multiselect("Filter podľa kategórie:", options=pending_cats, default=[], key="p_cats")
            
        st.write("---")
        
        for obj in pending_objs:
            # Filtering logic
            if p_search and p_search.lower() not in str(obj.data).lower():
                continue
            if p_cats and obj.category not in p_cats:
                continue
                
            with st.expander(f"[{obj.category}] ID: {obj.id}", expanded=False):
                metadata = obj.data.get("metadata", {})
                source = metadata.get("source_file", "Neznámy zdrojový súbor")
                chunk_index = metadata.get("source_chunk_idx", "N/A")
                source_text = metadata.get("source_text", "⚠️ Textový kontext nebol uložený pre tento starší objekt.")
                
                st.caption(f"Zdrojový súbor: **{source}** (Segment textu: #{chunk_index})")
                
                s1, s2 = st.columns([1.2, 1])
                
                with s1:
                    st.write("**📝 Parametre a Extrakcia (Možnosť editácie):**")
                    df_data = pd.DataFrame([obj.data])
                    
                    edited_df = st.data_editor(
                        df_data,
                        key=f"editor_{obj.id}",
                        use_container_width=True,
                    )
                    
                    edited_data = edited_df.to_dict('records')[0]
                    
                with s2:
                    st.write(f"**🔎 Pôvodný text odseku z `{source}`:**")
                    st.info(source_text, icon="📄")
                
                st.write("---")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Schváliť ako zdroj pravdy (Approve)", key=f"approve_{obj.id}", type="primary", use_container_width=True):
                        run_async(update_object_status(obj.id, "APPROVED", edited_data))
                        st.toast("✅ Objekt autorizovaný do CORE DATA!", icon="🏆")
                        st.rerun()
                with col2:
                    if st.button("Zamietnuť (Odstrániť)", key=f"reject_{obj.id}", use_container_width=True):
                        run_async(update_object_status(obj.id, "REJECTED"))
                        st.toast("❌ Objekt bol zamietnutý.", icon="🗑️")
                        st.rerun()

with tab_database:
    st.write("Finálne schválené znalostné objekty autoritatívnej vrstvy **CORE DATA**.")
    
    approved_objs = run_async(get_approved_objects())
    
    if not approved_objs:
        st.info("Zatiaľ neboli schválené žiadne objekty.")
    else:
        # Analytics / Metrics
        categories = [obj.category for obj in approved_objs]
        cat_counts = pd.Series(categories).value_counts().reset_index()
        cat_counts.columns = ["Kategória", "Počet"]
        
        col1, col2 = st.columns([1, 4])
        with col1:
            st.metric("Celkový počet objektov", len(approved_objs))
            st.caption("Rozdelenie podľa kategórií:")
            st.dataframe(cat_counts, use_container_width=True, hide_index=True)
            
            # Export
            export_data = [obj.data for obj in approved_objs]
            st.download_button(
                label="Stiahnuť všetko ako JSON", 
                data=json.dumps(export_data, ensure_ascii=False, indent=2), 
                file_name="core_data_export.json", 
                mime="application/json",
                use_container_width=True
            )
            
        with col2:
            st.write("**Katalóg objektov:**")
            
            # Filters
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                db_search = st.text_input("Hľadať (názov, popis, zdroj):", key="db_search")
            with f_col2:
                db_cats = st.multiselect("Filtrovať kategórie:", options=sorted(list(set(categories))), default=[], key="db_cats")
            
            # Flatten data for a beautiful table
            flat_data = []
            for obj in approved_objs:
                row = {
                    "ID": obj.id,
                    "Kategória": obj.category,
                    "Originálny názov": obj.data.get("original_name", ""),
                    "Názov (EN)": obj.data.get("name_en", ""),
                    "Popis": obj.data.get("description", ""),
                    "Zdroj": obj.data.get("metadata", {}).get("source_file", "")
                }
                
                # Apply Filters
                if db_cats and row["Kategória"] not in db_cats:
                    continue
                if db_search:
                    search_str = db_search.lower()
                    row_text = f"{row['Originálny názov']} {row['Názov (EN)']} {row['Popis']} {row['Zdroj']}".lower()
                    if search_str not in row_text:
                        continue
                        
                flat_data.append(row)
                
            if flat_data:
                st.dataframe(pd.DataFrame(flat_data), use_container_width=True, hide_index=True)
            else:
                st.warning("Zadaným filtrom nezodpovedajú žiadne dáta.")

