class AdaptiveCardTemplate:
    def __init__(self):
        self.root = {
            "type": "AdaptiveCard",
            "$schema": "https://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.5",
            "msteams": {"width": "full"},
            "body": [],
        }

    def add_text(
        self,
        content: str,
        is_title: bool = False,
        wrap: bool = True,
        color: str = "Default",
        spacing: str = "Default",
    ):
        self.root["body"].append(
            {
                "type": "TextBlock",
                "text": content,
                "weight": "Bolder" if is_title else "Default",
                "size": "ExtraLarge" if is_title else "Default",
                "wrap": wrap,
                "color": color,
                "spacing": spacing,
            }
        )

    def add_query_result_table(self, columns_info, data_info):
        table_generation = {
            "type": "Table",
            "gridStyle": "accent",
            "firstRowAsHeaders": True,
            "columns": [{"width": 1} for _ in range(columns_info["column_count"])],
            "rows": [],
        }

        # Create header row
        header_row = {"type": "TableRow", "cells": [], "style": "emphasis"}

        for column in columns_info["columns"]:
            header_row["cells"].append(
                {
                    "type": "TableCell",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": " ".join(column["name"].split("_")).capitalize(),
                            "wrap": True,
                            "weight": "Bolder",
                        }
                    ],
                }
            )

        table_generation["rows"].append(header_row)

        # Create data rows
        for row_data in data_info.get("data_array", []):
            data_row = {"type": "TableRow", "cells": []}

            for cell_value in row_data:
                data_row["cells"].append(
                    {
                        "type": "TableCell",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": str(cell_value),  # Ensure string conversion
                                "wrap": True,
                            }
                        ],
                    }
                )

            table_generation["rows"].append(data_row)

        self.root["body"].append(table_generation)

    def add_sql_code(self, query):
        self.root["body"].append(
            {
                "type": "ActionSet",
                "actions": [
                    {
                        "type": "Action.ToggleVisibility",
                        "title": "Show SQL",
                        "targetElements": ["sqlCode"],
                    }
                ],
            }
        )
        self.root["body"].append(
            {
                "type": "CodeBlock",
                "language": "Sql",
                "codeSnippet": query,
                "isVisible": False,
                "id": "sqlCode",
            }
        )

    def add_vertical_bar_chart(
        self,
        data,
        columns,
        show_bar_values: bool = True,
        chart_type: str = "Chart.VerticalBar",
    ):
        chart_base = {
            "title": "New Chart.VerticalBar",
            "type": chart_type,
            "colorSet": "categorical",
            "showBarValues": show_bar_values,
        }

        id_columns = []
        string_columns = []
        numeric_columns = []

        # Create column mappings for easy lookup
        column_map = {col["position"]: col["name"] for col in columns["columns"]}

        for col in columns["columns"]:
            col_name = col["name"].lower()
            if "id" in col_name:
                id_columns.append(col["position"])
            elif col["type_name"] == "STRING":
                string_columns.append(col["position"])
            elif col["type_name"] in ["LONG", "INT", "BIGINT", "DOUBLE", "FLOAT"]:
                numeric_columns.append(col["position"])

        # Find x and y column names
        x_column_name = None
        y_column_name = None
        x_column_pos = None
        y_column_pos = None

        # Get string column (x) - use first non-ID string column
        for pos in string_columns:
            if pos not in id_columns:
                x_column_name = column_map[pos]
                x_column_pos = pos
                break

        # Get numeric column (y) - use first non-ID numeric column
        for pos in numeric_columns:
            if pos not in id_columns:
                y_column_name = column_map[pos]
                y_column_pos = pos
                break

        # Process each row
        data_rows = []

        if x_column_pos is not None and y_column_pos is not None:
            for row in data.get("data_array", []):
                row_dict = {"x": row[x_column_pos], "y": float(row[y_column_pos])}
                data_rows.append(row_dict)

        chart_base["xAxisTitle"] = x_column_name
        chart_base["yAxisTitle"] = y_column_name
        chart_base["data"] = data_rows

        self.root["body"].append(chart_base)

    def add_donut_chart(self, data, columns, chart_type: str = "Chart.Donut"):
        chart_base = {
            "title": "New Chart.Donut",
            "data": [],
            "type": chart_type,
        }

        id_columns = []
        string_columns = []
        numeric_columns = []

        # Create column mappings for easy lookup
        column_map = {col["position"]: col["name"] for col in columns["columns"]}

        for col in columns["columns"]:
            col_name = col["name"].lower()
            if "id" in col_name:
                id_columns.append(col["position"])
            elif col["type_name"] == "STRING":
                string_columns.append(col["position"])
            elif col["type_name"] in ["LONG", "INT", "BIGINT", "DOUBLE", "FLOAT"]:
                numeric_columns.append(col["position"])

        # Find x and y column names
        x_column_name = None
        y_column_name = None
        x_column_pos = None
        y_column_pos = None

        # Get string column (x) - use first non-ID string column
        for pos in string_columns:
            if pos not in id_columns:
                x_column_name = column_map[pos]
                x_column_pos = pos
                break

        # Get numeric column (y) - use first non-ID numeric column
        for pos in numeric_columns:
            if pos not in id_columns:
                y_column_name = column_map[pos]
                y_column_pos = pos
                break

        # Process each row
        data_rows = []

        if x_column_pos is not None and y_column_pos is not None:
            for row in data.get("data_array", []):
                row_dict = {
                    "legend": row[x_column_pos],
                    "value": float(row[y_column_pos]),
                }
                data_rows.append(row_dict)

        chart_base["data"] = data_rows

        self.root["body"].append(chart_base)

    def add_grouped_bar_chart(
        self, data, columns, chart_type: str = "Chart.VerticalBar.Grouped"
    ):
        """
        Auto-detect the best X-axis (label) and legend string columns,
        and build a Chart.VerticalBar.Grouped card.
        """
        chart_base = {
            "title": "New Chart.VerticalBar.Grouped",
            "type": "Chart.VerticalBar.Grouped",
            "colorSet": "diverging",
            "data": [],
        }

        id_columns = []
        string_columns = []
        numeric_columns = []
        column_map = {col["position"]: col["name"] for col in columns["columns"]}

        for col in columns["columns"]:
            col_name = col["name"].lower()
            if "id" in col_name:
                id_columns.append(col["position"])
            elif col["type_name"] == "STRING":
                string_columns.append(col["position"])
            elif col["type_name"] in ["LONG", "INT", "BIGINT", "DOUBLE", "FLOAT"]:
                numeric_columns.append(col["position"])

        if len(string_columns) < 2 or not numeric_columns:
            return  # not enough columns

        # ---- Auto-detect best X and Legend columns ----
        # Compute unique counts for each string column
        unique_counts = {}
        rows = data.get("data_array", [])

        for pos in string_columns:
            unique_counts[pos] = len(
                set(row[pos] for row in rows if row[pos] is not None)
            )

        # Choose X-axis as column with largest unique values
        x_pos = max(unique_counts, key=unique_counts.get)
        # Choose Legend as the other string column with fewer uniques
        legend_candidates = [pos for pos in string_columns if pos != x_pos]
        legend_pos = min(legend_candidates, key=lambda p: unique_counts[p])

        # Use first numeric column
        y_pos = numeric_columns[0]

        x_axis_title = column_map[x_pos]
        y_axis_title = column_map[y_pos]

        # ---- Build grouped data structure ----
        grouped = {}
        for row in rows:
            x_val = row[x_pos]
            legend_val = row[legend_pos]
            y_val = float(row[y_pos])

            if legend_val not in grouped:
                grouped[legend_val] = []
            grouped[legend_val].append({"x": x_val, "y": y_val})

        # Fill chart data
        for legend, values in grouped.items():
            chart_base["data"].append({"legend": legend, "values": values})

        chart_base["xAxisTitle"] = x_axis_title
        chart_base["yAxisTitle"] = y_axis_title

        self.root["body"].append(chart_base)

    def add_stacked_horizontal_bar_chart(
        self,
        data,
        columns,
        chart_type: str = "Chart.HorizontalBar.Stacked",
    ):
        """
        Auto-detect legend series and build a Chart.HorizontalBar.Stacked card
        like the JSON you posted.
        """

        chart_base = {
            "title": "New Chart.HorizontalBar.Stacked",
            "type": chart_type,
            "colorSet": "sequential",
            "height": "stretch",
            "data": [],
        }

        id_columns = []
        string_columns = []
        numeric_columns = []
        column_map = {col["position"]: col["name"] for col in columns["columns"]}

        for col in columns["columns"]:
            col_name = col["name"].lower()
            if "id" in col_name:
                id_columns.append(col["position"])
            elif col["type_name"] == "STRING":
                string_columns.append(col["position"])
            elif col["type_name"] in ["LONG", "INT", "BIGINT", "DOUBLE", "FLOAT"]:
                numeric_columns.append(col["position"])

        # We need at least one string column for legend, one for category (x), one numeric
        if len(string_columns) < 2 or not numeric_columns:
            return  # not enough columns

        rows = data.get("data_array", [])

        # Compute unique counts to pick roles
        unique_counts = {
            pos: len(set(row[pos] for row in rows if row[pos] is not None))
            for pos in string_columns
        }

        # Category = the string col with most unique values (like date or x-axis)
        category_pos = max(unique_counts, key=unique_counts.get)
        # Series title = the other string col (fewest uniques)
        legend_candidates = [p for p in string_columns if p != category_pos]
        series_pos = min(legend_candidates, key=lambda p: unique_counts[p])

        y_pos = numeric_columns[0]

        # Group by the series (the outer titles in your JSON)
        series_grouped = {}
        for row in rows:
            series_title = row[series_pos]  # Outlook, Teams, etc.
            category_val = row[category_pos]  # e.g., date
            value_val = float(row[y_pos])

            if series_title not in series_grouped:
                series_grouped[series_title] = []

            series_grouped[series_title].append(
                {
                    "legend": category_val,
                    "value": value_val,
                }
            )

        # Fill chart data
        for series_title, values in series_grouped.items():
            chart_base["data"].append({"title": series_title, "data": values})

        self.root["body"].append(chart_base)

    def add_item(self, item):
        self.root["body"].append(item)

    def get_adaptive_card(self):
        return self.root
