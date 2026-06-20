"""
Utility for generating Excel files from Databricks SQL responses.
"""
import logging
from io import BytesIO
import polars
from uuid import uuid4
from typing import Tuple

logger = logging.getLogger(__name__)

class ExcelGenerator:
    """Handles the creation and formatting of Excel files from raw data arrays."""

    MAX_ROWS = 50000

    @staticmethod
    def generate_excel_from_data(data_array: list, columns: list) -> Tuple[str, BytesIO]:
        """
        Converts a raw JSON data array into an in-memory Excel file using Polars.

        Args:
            data_array (list): The list of dictionaries/rows returned by Genie.
            columns (list): The schema definition for the columns.

        Returns:
            Tuple[str, BytesIO]: The generated filename and the BytesIO buffer.
        """
        if len(data_array) > ExcelGenerator.MAX_ROWS:
            logger.warning(
                f"Result set too large ({len(data_array)} rows). Truncating to {ExcelGenerator.MAX_ROWS} rows."
            )
            data_array = data_array[:ExcelGenerator.MAX_ROWS]

        logger.debug("Creating Polars DataFrame.")
        df = polars.DataFrame(
            data=data_array,
            schema=[col["name"] for col in columns],
            orient="row",
        )

        excel_buffer = BytesIO()
        df.write_excel(excel_buffer)
        excel_buffer.seek(0)

        filename = f"{uuid4()}.xlsx"
        return filename, excel_buffer
