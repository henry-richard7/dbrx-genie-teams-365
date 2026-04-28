import json
import logging
from os import environ

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()
logger = logging.getLogger(__name__)
llm_endpoint = environ.get(
    "DATABRICKS_LLM_ENDPOINT", "databricks-qwen3-next-80b-a3b-instruct"
)


class LlmSummarizer:
    """LlmSummarizer: Generates concise summaries from datasets using a language model.

    This class provides a method to convert structured data into a textual summary
    and another method to generate a summary using a language model.
    """

    def __init__(self):
        self._models = {}
        self._workspace_clients = {}

    @staticmethod
    def dataframe_to_text(columns: list, data: list) -> str:
        """Convert a list of column definitions and data into a Markdown table representation.

        Parameters:
        columns (list of dict): List of column definitions (must have 'name' key).
        data (list of lists): The tabular data.

        Returns:
        str: A Markdown table representation of the data.
        """
        if not columns:
            return ""

        headers = [str(col["name"]) for col in columns]
        
        # Build Markdown table
        header_row = "| " + " | ".join(headers) + " |"
        separator = "| " + " | ".join("---" for _ in headers) + " |"
        
        rows = []
        for row in data:
            rows.append("| " + " | ".join(str(item) for item in row) + " |")
            
        return "\n".join([header_row, separator] + rows)

    def summarize(self, columns, data, question, client_id=None, client_secret=None):
        """Summarizes the given dataset using a chat model.

        Args:
            columns (list of dict): List of column definitions.
            data (list): Data to be summarized.
            question (str): User query to guide the summary.
            client_id (str, optional): Client ID for Databricks.
            client_secret (str, optional): Client secret for Databricks.

        Returns:
            str: A concise summary of the dataset based on the user query.
        """

        cache_key = client_id or "default"

        if cache_key not in self._models:
            kwargs = {
                "model": llm_endpoint,
                "temperature": 0.1,
            }

            base_url = environ.get("model_base_url")
            if base_url:
                kwargs["base_url"] = base_url

            kwargs["api_key"] = environ.get("OPENAI_API_KEY")

            if not kwargs["api_key"] or kwargs["api_key"] == "not-provided":
                logger.debug("Attempting to get token from Databricks WorkspaceClient")
                from databricks.sdk import WorkspaceClient

                host = environ.get("DATABRICKS_HOST")

                try:
                    # Cache the WorkspaceClient to reuse authentication session
                    if cache_key not in self._workspace_clients:
                        if client_id and client_secret:
                            self._workspace_clients[cache_key] = WorkspaceClient(
                                host=host, client_id=client_id, client_secret=client_secret
                            )
                        else:
                            self._workspace_clients[cache_key] = WorkspaceClient(host=host)
                    
                    w = self._workspace_clients[cache_key]
                    creds = w.config.authenticate()
                    if creds and isinstance(creds, dict) and "Authorization" in creds:
                        kwargs["api_key"] = creds.get("Authorization").replace("Bearer ", "")
                    elif w.config.token:
                        kwargs["api_key"] = w.config.token
                    
                    if "base_url" not in kwargs and host:
                        kwargs["base_url"] = f"{host.rstrip('/')}/serving-endpoints"
                except Exception as e:
                    logger.error(f"Error initializing Databricks WorkspaceClient: {e}")

            if not kwargs.get("api_key"):
                kwargs["api_key"] = "not-provided"

            self._models[cache_key] = ChatOpenAI(**kwargs)

        model = self._models[cache_key]

        # Convert data to Markdown table directly without pandas
        table_text = self.dataframe_to_text(columns, data)

        prompt_template = """
            You are an expert data analyst. Below is a dataset.

            Your task is to analyze the data and provide a JSON response. 
            The JSON MUST have two keys:
            1. "text": A Markdown formatted string containing:
               - **Summary**: A concise, insightful summary (2-4 sentences) of the key trends.
               - **Next Best Action**: A recommendation based on the data.
            2. "chart": A string representing the best chart type to visualize this data. 
               Choose from: ["Chart.VerticalBar", "Chart.HorizontalBar.Stacked", "Chart.Donut", "Chart.VerticalBar.Grouped", null]. 
               Use null if the data is not suitable for a chart (e.g. detailed row-level data or non-aggregated data).

            Dataset:
            {data}

            User Query:
            {query}
            
            Return ONLY valid JSON. Do not include markdown code blocks like ```json.
            """

        formatted_prompt = prompt_template.format(data=table_text, query=question)

        # Request completion
        response = model.invoke(formatted_prompt)

        if hasattr(response, "content"):
            response_content = response.content
        else:
            response_content = str(response)

        # Strip markdown code blocks if the LLM adds them
        response_content = response_content.strip()
        if response_content.startswith("```json"):
            response_content = response_content[7:]
        if response_content.startswith("```"):
            response_content = response_content[3:]
        if response_content.endswith("```"):
            response_content = response_content[:-3]
        response_content = response_content.strip()

        # Parse the JSON response
        try:
            parsed_response = json.loads(response_content)
            
            # Extract standard dict response
            if isinstance(parsed_response, dict) and "text" in parsed_response:
                return parsed_response

            # Handle Databricks AI Gateway legacy list format
            if isinstance(parsed_response, list):
                for item in parsed_response:
                    if isinstance(item, dict) and item.get("type") == "text" and "text" in item:
                        # Try to parse the inner text as JSON
                        try:
                            inner_parsed = json.loads(item["text"])
                            if isinstance(inner_parsed, dict) and "text" in inner_parsed:
                                return inner_parsed
                        except json.JSONDecodeError:
                            return {"text": item["text"], "chart": None}

            return {"text": response_content, "chart": None}
        except (json.JSONDecodeError, TypeError):
            return {"text": response_content, "chart": None}
