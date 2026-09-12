"""
LLM summarizer module.

Provides the LlmSummarizer class which uses an LLM to generate insights
and recommend chart types from tabular data.
"""
import json
import logging
from os import environ

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()
logger = logging.getLogger(__name__)
llm_endpoint = environ.get(
    "OPENAI_MODEL_NAME", "databricks-qwen3-next-80b-a3b-instruct"
)

from utils.llm_client_base import BaseLLMClient


class LlmSummarizer(BaseLLMClient):
    """Generates concise summaries from Databricks SQL datasets using a language model.

    This class provides a method to convert structured data into a textual representation
    (Markdown table) and a method to generate an analytical summary and recommend charts
    using a configured ChatOpenAI model.

    Model instances are cached per credential scope and automatically refreshed after
    55 minutes so that short-lived Databricks OAuth tokens do not silently expire.
    """

    @staticmethod
    def dataframe_to_text(columns: list, data: list) -> str:
        """Converts a list of column definitions and data into a Markdown table representation.

        Args:
            columns (list): List of column definitions (must have 'name' key).
            data (list): The tabular row data.

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

    def summarize(
        self,
        columns: list,
        data: list,
        question: str,
        client_id: str = None,
        client_secret: str = None,
    ) -> dict:
        """Summarizes the given dataset using a configured language model.

        Converts the data to a Markdown table and prompts the LLM to return a structured
        JSON response containing an analytical summary, next best action, and a chart recommendation.

        Args:
            columns (list): List of column definitions.
            data (list): Data to be summarized.
            question (str): The user query to guide the summary context.
            client_id (str, optional): OAuth Client ID for Databricks. Defaults to None.
            client_secret (str, optional): OAuth Client Secret for Databricks. Defaults to None.

        Returns:
            dict: A dictionary containing 'text' (the summary) and 'chart' (the recommended chart type).
        """

        model = self._get_or_create_model(client_id, client_secret, temperature=0.1)
        if model is None:
            return {
                "text": "⚠️ **AI Insights Unavailable**\n\nFailed to authenticate or initialize model.",
                "chart": None,
            }

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
            
            Return ONLY valid JSON. Do not include thinking or reasoning traces, preambles, or markdown code blocks.
            """

        formatted_prompt = prompt_template.format(data=table_text, query=question)

        # Request completion
        try:
            response = model.invoke(formatted_prompt)
        except Exception as e:
            logger.warning(f"LLM API failed or rate limit reached: {e}")
            return {
                "text": "⚠️ **AI Insights Unavailable**\n\nThe AI assistant is currently experiencing high demand or reached its rate limits. Your raw data results are provided below.",
                "chart": None,
            }

        response_content = self._parse_json_response(response)

        # Parse the JSON response
        try:
            parsed_response = json.loads(response_content)

            # Extract standard dict response
            if isinstance(parsed_response, dict) and "text" in parsed_response:
                return parsed_response

            # Handle Databricks AI Gateway legacy list format
            if isinstance(parsed_response, list):
                for item in parsed_response:
                    if (
                        isinstance(item, dict)
                        and item.get("type") == "text"
                        and "text" in item
                    ):
                        # Try to parse the inner text as JSON
                        try:
                            inner_parsed = json.loads(item["text"])
                            if (
                                isinstance(inner_parsed, dict)
                                and "text" in inner_parsed
                            ):
                                return inner_parsed
                        except json.JSONDecodeError:
                            return {"text": item["text"], "chart": None}

            return {"text": response_content, "chart": None}
        except (json.JSONDecodeError, TypeError):
            return {"text": response_content, "chart": None}
