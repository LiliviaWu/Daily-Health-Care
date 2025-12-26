import os
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    EMBEDDING_MODEL,
    PERSON_KB_PATH,
)

# 定义文件夹路径
DATA_PATH    = "person_basic_info"  # 你的文档所在文件夹
DB_SAVE_PATH = PERSON_KB_PATH     # 向量数据库保存路径

def create_vector_db():
    print("🔄 开始加载文档...")
    
    docs = []
    
    # 1. 加载 PDF 文件
    if os.path.exists(DATA_PATH):
        # 加载 PDF
        pdf_loader = DirectoryLoader(DATA_PATH, glob="**/*.pdf", loader_cls=PyPDFLoader)
        pdf_docs = pdf_loader.load()
        docs.extend(pdf_docs)
        print("已加载的 PDF 文件:", list(set(doc.metadata["source"] for doc in pdf_docs)))
        # print(f"   - 加载了 {len(pdf_docs)} 个 PDF 文档")

    else:
        print(f"❌ 错误：找不到文件夹 '{DATA_PATH}'，请先创建并放入文件。")
        return

    if not docs:
        print("❌ 未找到任何文件，请检查文件夹内容。")
        return

    # 2. 文本切分 (Text Splitter)
    # 使用与你 Notebook 中类似的切分参数
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,  # 每个块的大小
        chunk_overlap=200 # 上下文重叠部分
    )
    splits = text_splitter.split_documents(docs)
    print(f"✂️  文档已切分为 {len(splits)} 个片段")

    # 3. 初始化 Embedding 模型
    embeddings = OpenAIEmbeddings(
        base_url=OPENAI_BASE_URL,
        api_key=OPENAI_API_KEY,
        model=EMBEDDING_MODEL # 推荐使用此模型，性价比高
    )

    # 4. 向量化并存入 FAISS
    print("zzZ  正在生成向量并存入 FAISS (这可能需要一点时间)...")
    vector_store = FAISS.from_documents(splits, embeddings)

    # 5. 保存到本地磁盘
    vector_store.save_local(DB_SAVE_PATH)
    print(f"✅ 成功！数据库已保存至本地文件夹: ./{DB_SAVE_PATH}")

# --- 测试加载与检索 ---
def test_query(query_text):
    print(f"\n🔍 测试检索: {query_text}")
    
    # 重新加载 Embedding (用于查询)
    embeddings = OpenAIEmbeddings(
        base_url=OPENAI_BASE_URL,
        api_key=OPENAI_API_KEY,
        model=EMBEDDING_MODEL
    )
    
    # 加载本地保存的数据库
    # allow_dangerous_deserialization=True 是为了加载 pickle 文件，确信文件是自己生成的即可
    new_vector_store = FAISS.load_local(
        DB_SAVE_PATH, 
        embeddings, 
        allow_dangerous_deserialization=True
    )
    
    # 执行相似度搜索
    results = new_vector_store.similarity_search(query_text, k=2)
    
    for i, doc in enumerate(results):
        source = doc.metadata.get("source", "未知来源")
        content = doc.page_content[:100] + "..." # 只显示前100字
        print(f"   [结果 {i+1}] (来源: {source}):\n   {content}\n")

if __name__ == "__main__":
    # 第一步：建立数据库
    create_vector_db()
    
    # 第二步：简单测试 (确保 person_basic_info 文件夹存在且有文件后再运行)
    # test_query("高血压防治的关键是什么？")
