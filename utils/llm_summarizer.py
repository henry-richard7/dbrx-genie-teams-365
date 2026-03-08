import json
import logging
from os import environ

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import polars as pl

load_dotenv()
logger = logging.getLogger(__name__)
llm_endpoint = environ.get(
    "DATABRICKS_LLM_ENDPOINT", "databricks-qwen3-next-80b-a3b-instruct"
)


class LlmSummarizer:
    """LlmSummarizer: Generates concise summaries from datasets using a language model.

    This class provides a method to convert a polars DataFrame into a textual summary
    and another method to generate a summary from structured data using a language model.
    """

    @staticmethod
    def dataframe_to_text(df: pl.DataFrame) -> str:
        """Convert a polars DataFrame to a string representation.

        Parameters:
        df (pl.DataFrame): The DataFrame to be converted.

        Returns:
        str: A string representation of the DataFrame.
        """
        with pl.Config(
            tbl_rows=-1,
            tbl_cols=-1,
            tbl_hide_dataframe_shape=True,
            tbl_hide_column_data_types=True,
        ):
            return str(df)

    def summarize(self, columns, data, question, client_id=None, client_secret=None):
        """Summarizes the given dataset using a chat model.

        Args:
            columns (list of dict): List of column definitions.
            data (list): Data to be summarized.
            question (str): User query to guide the summary.

        Returns:
            str: A concise summary of the dataset based on the user query.
        """

        kwargs = {
            "model": llm_endpoint,
            "temperature": 0.1,
        }

        base_url = environ.get("model_base_url")
        if base_url:
            kwargs["base_url"] = base_url

        kwargs["api_key"] = environ.get("OPENAI_API_KEY", "not-provided")

        use_databricks_model = (
            environ.get("use_databricks_model", "false").lower() == "true"
        )

        if use_databricks_model and client_id and client_secret:
            logger.debug(f"Initializing ChatOpenAI with client_id: {client_id}")
            from databricks.sdk import WorkspaceClient

            # Use databricks sdk to configure the workspace client directly
            host = environ.get(
                "DATABRICKS_HOST",
            )

            try:
                # Initialize WorkspaceClient to get token for AI Gateway
                w = WorkspaceClient(
                    host=host, client_id=client_id, client_secret=client_secret
                )
                creds = w.config.authenticate()
                if creds:
                    kwargs["api_key"] = creds.get("Authorization").replace(
                        "Bearer ", ""
                    )
            except Exception as e:
                logger.error(f"Error initializing Databricks WorkspaceClient: {e}")
        else:
            logger.debug("Initializing ChatOpenAI without explicit client credentials")

        model = ChatOpenAI(**kwargs)
        df = pl.DataFrame(data, schema=[col["name"] for col in columns], orient="row")

        table_text = self.dataframe_to_text(df)

        prompt_template = """
            You are an expert data analyst. Below is a dataset.

            Your task is to analyze the data and provide a response formatted in Markdown for Microsoft Teams:
            - Use **Bold** for headers.
            - Use bullet points for lists.
            
            Provide:
            1. **Summary**: A concise, insightful summary (2-4 sentences) of the key trends or observations.
            2. **Next Best Action**: A recommendation based on the data.

            Dataset:
            {data}

            User Query:
            {query}
            """

        formatted_prompt = prompt_template.format(data=table_text, query=question)

        # Request completion
        response = model.invoke(formatted_prompt)

        if hasattr(response, "content"):
            response_content = response.content
        else:
            response_content = str(response)

        # The LLM may return a JSON string with reasoning and text parts.
        # We need to parse it and extract the user-facing text.
        try:
            parsed_response = json.loads(response_content)
            # The response is expected to be a list of dictionaries
            if isinstance(parsed_response, list):
                for item in parsed_response:
                    # We are interested in the part with type 'text'
                    if (
                        isinstance(item, dict)
                        and item.get("type") == "text"
                        and "text" in item
                    ):
                        return item["text"]
            # If the expected structure isn't found, return the raw content as a fallback.
            return response_content
        except (json.JSONDecodeError, TypeError):
            # If JSON parsing fails, assume it's the direct text response.
            return response_content
