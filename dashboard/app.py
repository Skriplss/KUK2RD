import streamlit as st
import asyncio
import pandas as pd
from src.services.parser import DocumentParser
from src.services.interpreter import extract_knowledge_from_chunk
from src.services.validator import Validator
from src.core.database import init_db, AsyncSessionLocal, KnowledgeObject
from src.utils.logger import get_logger

logger = get_logger(__name__)

st.set_page_config(page_title="KUK2RD Dashboard", layout="wide")
st.title("KUK2RD - Curator Dashboard")
st.write("Nahrajte odborné PDF na extrakciu dát pomocou znalostného systému.")

@st.cache_resource
def setup_db():
    if "db_initialized" not in st.session_state:
        asyncio.run(init_db())
        st.session_state.db_initialized = True

setup_db()

async def save_approved_objects(approved_items: list):
    async with AsyncSessionLocal() as session:
        for item in approved_items:
            db_obj = KnowledgeObject(
                category=item.get("category", "Unknown"),
                data=item,
                status="APPROVED"
            )
            session.add(db_obj)
        await session.commit()

async def process_pdf_workflow(file_bytes: bytes, progress_bar, file_ext: str):
    try:
        if file_ext == "pdf":
            text = DocumentParser.extract_text_from_pdf(file_bytes)
        elif file_ext == "docx":
            text = DocumentParser.extract_text_from_docx(file_bytes)
        else:
            return []
    except Exception as e:
        logger.error(f"Error analyzing document: {e}")
        st.error(f"Chyba pri čítaní dokumentu: {e}")
        return []

    chunks = DocumentParser.chunk_text(text)
    st.info(f"Sémantické rozdelenie textu na {len(chunks)} odsekových blokov. Spúšťa sa AI extrakcia...")
    
    all_extracted = []
    for i, chunk in enumerate(chunks):
        if chunk.strip():
            items = await extract_knowledge_from_chunk(chunk)
            validated_items = Validator.validate_extracted_items(items)
            all_extracted.extend(validated_items)
        progress_bar.progress((i + 1) / len(chunks))

    st.success("Extrakcia úspešne dokončená.")
    return all_extracted

uploaded_file = st.file_uploader("Vyberte dokument (PDF, DOCX)", type=["pdf", "docx"])

if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = []

if uploaded_file is not None and st.button("Spracovať dokument"):
    progress_bar = st.progress(0)
    with st.spinner("Spracovávam dokument. Toto môže chvíľku trvať..."):
        file_bytes = uploaded_file.read()
        file_ext = uploaded_file.name.split('.')[-1].lower()
        extracted_items = asyncio.run(process_pdf_workflow(file_bytes, progress_bar, file_ext))
        
        for item in extracted_items:
            item["Schváliť"] = False
        st.session_state.extracted_data = extracted_items

if st.session_state.extracted_data:
    st.subheader("Navrhované objekty na schválenie (CORE DATA)")
    df = pd.DataFrame(st.session_state.extracted_data)
    edited_df = st.data_editor(
        df, 
        column_order=["Schváliť", "category", "name_en", "original_name", "description"],
        disabled=[col for col in df.columns if col != "Schváliť"],
        use_container_width=True
    )
    
    if st.button("Uložiť schválené do DB"):
        approved_rows = edited_df[edited_df["Schváliť"] == True].drop(columns=["Schváliť"]).to_dict('records')
        
        if approved_rows:
            with st.spinner("Ukladám do databázy so statusom APPROVED..."):
                asyncio.run(save_approved_objects(approved_rows))
            st.success(f"{len(approved_rows)} objektov bolo uložených do CORE DATA!")
            remaining = edited_df[edited_df["Schváliť"] == False].to_dict('records')
            st.session_state.extracted_data = remaining
            st.rerun()
        else:
            st.warning("Nevybrali ste žiadne dáta na schválenie.")
