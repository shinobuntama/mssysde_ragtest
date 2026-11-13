from azure.cosmos import CosmosClient, exceptions
import os


class CosmosService:

    def __init__(self) -> None:
        """CosmosDBのクライアントを初期化する。
        """
        self.client = CosmosClient(
            url=os.getenv('COSMOS_URL'),
            credential=os.getenv('COSMOS_CREDENTIAL')
        )
        self.database = self.client.get_database_client(
            os.getenv('COSMOS_DATABASE_NAME'))
        self.container = self.database.get_container_client(
            os.getenv('COSMOS_CONTAINER_NAME'))

    def upsert_item(self, item) -> None:
        """CosmosDBにアイテムを追加または更新する。

        Args:
            item (_type_): 追加または更新するアイテム
        """
        try:
            print('Upserting CosmosDB.')
            self.container.upsert_item(item)
            print('Upserted CosmosDB.')

        except exceptions.CosmosHttpResponseError as e:
            print(f'error! CosmosHttpResponseError at upsert_item: {e}')
            raise e

        except Exception as e:
            print(f'error! Error at upsert_item: {e}')
            raise

    def get_item(self, query) -> dict:
        """CosmosDBからアイテムを取得する。

        Args:
            query (_type_): クエリ

        Returns:
            dict: CosmosDBから取得したアイテム
        """
        try:
#            print('Querying CosmosDB.')
#            print(f'query: {query}')

#            items = self.container.query_items(
 #               query=query,
  #              enable_cross_partition_query=True
                
   #         )
            
            print('Getting CosmosDB.')
            items = self.container.query_items(
                query,enable_cross_partition_query=True)
            print('Got CosmosDB.')
            return items

        except exceptions.CosmosHttpResponseError as e:
            print(f'error! CosmosHttpResponseError at get_item: {e}')
            raise e

        except Exception as e:
            print(f'error! Error at get_item: {e}')
            raise e

    def delete_item(self, item_id) -> None:
        """CosmosDBからアイテムを削除する。

        Args:
            item_id (_type_): 削除するアイテムのID
        """
        try:
            print('Deleting CosmosDB.')
            self.container.delete_item(item_id, partition_key=item_id)
            print('Deleted CosmosDB.')

        except exceptions.CosmosHttpResponseError as e:
            print(f'error! CosmosHttpResponseError at delete_data: {e}')
            raise e

        except Exception as e:
            print(f'error! Error at delete_data: {e}')
            raise e

    def get_items_by_vector(self, embedding, VECTOR_SCORE_THRESHOLD) -> list:
        """ベクトル検索でCosmosDBからアイテムを取得する。

        Args:
            embedding (_type_): 検索クエリのベクトル値
            VECTOR_SCORE_THRESHOLD (_type_): ベクトルスコアのしきい値

        Returns:
            list: CosmosDBから取得したアイテムのリスト
        """

        try:
            print('Querying CosmosDB.')
            print(f'vectorScore: {VECTOR_SCORE_THRESHOLD}')

            query = f"""SELECT TOP 10 c.file_name, c.page_number, c.content
            FROM c 
            ORDER BY VectorDistance(c.vector, @embedding)"""
            parameters = [
                {'name': '@embedding', 'value': embedding}
            ]

            items = self.container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            )

            resources = [item for item in items]
            for item in resources:
                print(
                    f'{item["file_name"]}, {item["page_number"]}, {item["content"]} is a capitol \n')

            return resources

        except exceptions.CosmosHttpResponseError as e:
            print(f'x CosmosHttpResponseError at get_items_by_vector: {e}')
            raise e

        except Exception as e:
            print(f'x Error at get_items_by_vector: {e}')
            raise e
