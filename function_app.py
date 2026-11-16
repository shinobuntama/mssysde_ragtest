import azure.functions as func
import logging
import os
import json
import uuid

from azure.storage.blob import BlobServiceClient
from util.cosmos_service import CosmosService
from util.openai_service import AzureOpenAIService
from domain.cosmos_document import CosmosDocument
from util.document_parser import parse_pdf, parse_excel, parse_docx, parse_image
from util.chunker import chunk_pages

app = func.FunctionApp()

# 環境変数
# COSMOS_CONNECTION = os.getenv('COSMOS_CONNECTION')
COSMOS_DATABASE_NAME = os.getenv('COSMOS_DATABASE_NAME')
COSMOS_CONTAINER_NAME = os.getenv('COSMOS_CONTAINER_NAME')
BLOB_CONNECTION = os.getenv('BLOB_CONNECTION')

# client
openai_service = AzureOpenAIService()
cosmos_service = CosmosService()
blob_service_client = BlobServiceClient.from_connection_string(BLOB_CONNECTION)

@app.cosmos_db_trigger(arg_name="azcosmosdb", container_name=COSMOS_CONTAINER_NAME,
                        database_name=COSMOS_DATABASE_NAME, connection="cosmosrageventdriven_DOCUMENTDB")  
def cosmosdb_trigger(azcosmosdb: func.DocumentList):
    """
    CosmosDBの登録、更新、削除をトリガーに実行され、vector_update_flagがTrueの場合にベクトル値を更新する
    {
        "id": "631762fb-489c-4898-bfe8-0bcef21ab9ae",
        "content": "# タイトル\nrag-docs/test/2024-01~03月GDP.pdf\n### 2024年1〜3月期四半期別GDP速報（1次速報値）\n\n**Quarterly Estimates of GDP for January - March 2024 (First Preliminary Estimates)**\n\n**発表日**: 令和6年5月16日  \n**発表機関**: 内閣府経済社会総合研究所 国民経済計算部\n\n#### I. 国内総生産（支出側）及び各需要項目\n**GDP (Expenditure Approach) and Its Components**\n\n#### 1. ポイント\n**Main Points (Japanese)**\n\n**[1] GDP成長率（季節調整済前期比）**\n- 2024年1〜3月期の実質GDP（国内総生産：2015年基準連鎖価格）の成長率は、▲0.5%（年率▲2.0%）となった。また、名目GDPの成長率は、0.1%（年率0.4%）となった。\n\n| (%) | 実質GDP成長率の推移 | 名目GDP成長率の推移 |\n|-----|---------------------|---------------------|\n| 2023 | 1.2 | 2.2 |\n| 4-6  | 1.0 | 2.6 |\n| 7-9  | 0.0 | 0.0 |\n| 10-12| -0.9| -1.3|\n| 2024 | -0.5| 0.1 |\n\n**[2] GDPの内外需の寄与度**\n- GDP成長率のうち、どの需要がGDPをどれだけ増減させたかを示す寄与度でみると、実質は国内需要（内需）が▲0.2%、財貨・サービスの純輸出（輸出-輸入）が▲0.3%となった。また、名目は国内需要（内需）が0.5%、財貨・サービスの純輸出（輸出-輸入）が▲0.4%となった。\n\n| (%) | 実質GDPの内外需寄与度の推移 | 名目GDPの内外需寄与度の推移 |\n|-----|---------------------------|---------------------------|\n| 2023 | 1.2 | 0.5 |\n| 4-6  | 0.7 | 2.3 |\n| 7-9  | 0.0 | 0.7 |\n| 10-12| -0.2| 0.3 |\n| 2024 | -0.2| 0.5 |\n\n**内外需寄与度**\n- 実質GDPの内外需寄与度の推移\n- 名目GDPの内外需寄与度の推移",
        "vector": [],
        "file_name": "test/2024-01~03月GDP.pdf",
        "file_path": "https://saragextra1.blob.core.windows.net/rag-docs/test/2024-01~03月GDP.pdf",
        "vector_update_flag": false
    }
    """

    logging.info('Python CosmosDB triggered.')

    try:
        for doc in azcosmosdb:
            doc_document = CosmosDocument(**doc)

            # ベクトル更新フラグがTrueの場合のみベクトル値を更新
            if doc_document.vector_update_flag:
                logging.info(
                    f'Start update vector: {doc_document.file_name}')

                # ベクトル値を取得
                embedding = openai_service.getEmbedding(doc_document.content)

                # CosmosDBにベクトル値を更新
                doc_document.vector = embedding
                doc_document.vector_update_flag = False
                cosmos_service.upsert_item(doc_document.dict())
                logging.info(
                    f'Finish update vector: {doc_document.file_name}')
        
    except Exception as e:
        logging.error(f'Error: {e}')
        raise e

@app.event_grid_trigger(arg_name="azeventgrid")
def EventGridTrigger(azeventgrid: func.EventGridEvent):
    """EventGridTriggerで、Blobの作成、削除イベントをトリガーとして、Blobファイルの内容をCosmosDBに登録する
    - Blobの作成イベントの場合、Blobファイルの内容をCosmosDBに登録する。ファイル更新も作成イベントとして扱われるため、同じファイルパスがCosmosDBに登録されている場合はCosmosDBのアイテムを削除する。
    - Blobの削除イベントの場合、CosmosDBのアイテムを削除する

    EventGridTriggerイベントはREST通信で以下のBody形式で送信される
    {
        "id": "1",
        "eventType": "Microsoft.Storage.BlobCreated",
        "subject": "/blobServices/default/containers/rag-docs/blobs/（２）令和６年度の経済動向.md",
        "eventTime": "2024-08-11T17:02:19.6069787Z",
        "data": {
            "api": "PutBlob",
            "clientRequestId": "2168279a-2557-4782-a60d-bca035d23023",
            "requestId": "d7b8cabe-801e-001f-52df-ebf109000000",
            "eTag": "0x8DCB9F71B061CD3",
            "contentType": "application/pdf",
            "contentLength": 2381873,
            "blobType": "BlockBlob",
            "url": "https://sarageventdriven.blob.core.windows.net/rag-docs/（２）令和６年度の経済動向.md",
            "sequencer": "00000000000000000000000000012F09000000000003ceb0",
            "storageDiagnostics": {
            "batchId": "5e7b9236-0006-004c-00df-ebd23d000000"
            }
        },
        "dataVersion": "1.0"
    }

    Args:
        azeventgrid (func.EventGridEvent): EventGridEvent

    Returns:
        None

    Raises:
        e: Exception
    """

    event = json.dumps({
        'id': azeventgrid.id,
        'event_type': azeventgrid.event_type,
        'data': azeventgrid.get_json(),
    })

    # eventを辞書型に変換
    event_dict = json.loads(event)
#    blob_url = event_dict.get('data').get('url')
    blob_url = event_dict['data']['url']

    logging.info(f"blob_url = [{blob_url}]")
    
    logging.info(f'Python EventGrid trigger: {event_dict}')
    try:
        # event_typeがBlobCreatedの場合
        if event_dict.get('event_type') == 'Microsoft.Storage.BlobCreated':

            logging.info(f'🚀 Event Type: {event_dict.get("event_type")}')

            # Blobファイルの内容を取得
            blob_name = blob_url.split("rag-docs/")[1]
            logging.info(f'🚀 Blob Name: {blob_name}')
            blob_client = blob_service_client.get_blob_client(
                container='rag-docs', blob=blob_name)
            blob_data = blob_client.download_blob()
            logging.info(f'🚀 Blob File Downloaded.')

            # ファイル名と拡張子を取得
            file_name = blob_data.name
            file_extension = os.path.splitext(file_name)[1]

            logging.info(f'🚀 File Name: {file_name}')
            logging.info(f'🚀 File Extension: {file_extension}')

            rag_docs = blob_data.content_as_bytes()

            # 同じblob_urlがCosmosDBに登録されている場合はCosmosDBのアイテムを削除
            query = f"SELECT * FROM c WHERE c.file_path = '{blob_url}'"
            items = cosmos_service.get_item(query)
            for item in items:
                # CosmosDBのアイテムを削除
                cosmos_service.delete_item(item['id'])
                logging.info(
                    f'🚀 Deleted CosmosDB item: {item["file_name"]}')

            # 拡張子ごとに (ページ番号, 本文) のリストを作る
            ext = file_extension.lower()
            if ext in (".txt", ".md"):
                logging.info("🚀 Trigger blob file is Text or Markdown")
                pages = [(0, rag_docs.decode('utf-8'))]
            elif ext == ".pdf":
                logging.info("🚀 Trigger blob file is PDF")
                pages = parse_pdf(rag_docs)
            elif ext in (".xls", ".xlsx"):
                logging.info("🚀 Trigger blob file is Excel")
                pages = parse_excel(rag_docs, ext)
            elif ext == ".docx":
                logging.info("🚀 Trigger blob file is Word")
                pages = parse_docx(rag_docs)
            elif ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
                # 画像はOCR(Document Intelligence)で文字を読み取る
                logging.info("🚀 Trigger blob file is Image (OCR)")
                pages = parse_image(rag_docs)
            elif ext == ".doc":
                # 旧形式(.doc)は python-docx で読めないため非対応
                logging.warning(
                    '❌ .doc is not supported. Please convert to .docx')
                pages = []
            else:
                logging.warning(
                    f'❌ Unsupported file type: {file_extension}')
                pages = []

            # チャンキング(見出し・表の構造を優先し、長い部分は文単位で分割)
            # PDFは全ページを連結してから分割し、Excelはシートごとに独立して分割する
            chunks = chunk_pages(pages, merge_pages=(ext == ".pdf"))
            logging.info(f'🚀 Chunks: {len(chunks)} (from {len(pages)} page/sheet units)')

            # チャンクごとにCosmosDBへ登録
            for page_number, body in chunks:
                cosmos_obj = CosmosDocument(
                    id=str(uuid.uuid4()),
                    file_name=file_name,
                    file_path=blob_url,
                    page_number=page_number,
                    # ファイル名をタイトルとして、コンテンツをMarkdown形式にする
                    content=f'# {file_name}\n\n{body}',
                    vector=[],
                    keywords=[],
                    delete_flag=False,
                    vector_update_flag=True
                )
                cosmos_service.upsert_item(cosmos_obj.to_dict())

        # event_typeがBlobDeletedの場合
        elif event_dict.get('event_type') == 'Microsoft.Storage.BlobDeleted':
            logging.info(f'🚀Event Type: {event_dict.get("event_type")}')
    
            # blob_urlがCosmosDBに登録されている場合はCosmosDBのアイテムを削除
            query = f"SELECT * FROM c WHERE c.file_path = '{blob_url}'"
            items = cosmos_service.get_item(query)

            for item in items:
                # CosmosDBのアイテムを削除
                cosmos_service.delete_item(item['id'])
                logging.info(
                    f'🚀Deleted CosmosDB item: {item["file_name"]}')

        else:
            logging.warning(
                f'❌Unsupported event type: {event_dict.get("event_type")}')

    except Exception as e:
        logging.error(f'❌Error: {e}')
        raise e
    