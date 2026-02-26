/** @odoo-module */

import { registry } from "@web/core/registry";
import { JournalDashboardGraphField } from "@web/views/fields/journal_dashboard_graph/journal_dashboard_graph_field";
import { getColor } from "@web/core/colors/colors";
import { cookie } from "@web/core/browser/cookie";

export class SalesCatalogDashboardGraphField extends JournalDashboardGraphField {
    static template = "web.JournalDashboardGraphField";

    getBarChartConfig() {
        const data = Array.isArray(this.data) ? this.data : [];
        const first = data[0];
        if (!first || !Array.isArray(first.values)) {
            return {
                type: "bar",
                data: { labels: [], datasets: [] },
                options: {
                    plugins: { legend: { display: false }, tooltip: { enabled: true } },
                    scales: { y: { stacked: true, display: false }, x: { stacked: true, display: false } },
                    maintainAspectRatio: false,
                },
            };
        }

        const labels = first.values.map(pt => pt.label);

        const datasets = data.map(dataset => {
            const values = Array.isArray(dataset.values) ? dataset.values : [];
            const chartData = values.map(pt => pt.value);
            // Use the color defined at the dataset level in Python
            const backgroundColor = dataset.color || getColor(0, cookie.get("color_scheme"), "odoo");

            return {
                label: dataset.key || "",
                data: chartData,
                backgroundColor: backgroundColor,
                fill: "start",
                stack: 'Stack 0', // Enable stacking
            };
        });

        return {
            type: "bar",
            data: {
                labels,
                datasets,
            },
            options: {
                plugins: {
                    legend: { display: false }, // Keep it clean or enable if user wants legend
                    tooltip: {
                        enabled: true, // Enable tooltips
                        intersect: false,
                        position: "nearest",
                        caretSize: 0,
                    },
                },
                scales: {
                    y: {
                        stacked: true, // Enable stacking on Y
                        display: false,
                    },
                    x: {
                        stacked: true, // Enable stacking on X
                        display: false,
                    },
                },
                maintainAspectRatio: false,
                elements: {
                    line: {
                        tension: 0.000001,
                    },
                },
            },
        };
    }

    getPieChartConfig() {
        const data = Array.isArray(this.data) ? this.data : [];
        if (!data.length) {
            return {
                type: "doughnut",
                data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderWidth: 1 }] },
                options: {
                    plugins: { legend: { display: true, position: "right" }, tooltip: { enabled: true } },
                    maintainAspectRatio: false,
                    cutout: "60%",
                },
            };
        }
        const labels = data.map((dataset) => dataset.key || "");
        const chartData = data.map((dataset) => {
            const values = Array.isArray(dataset.values) ? dataset.values : [];
            return values.reduce((sum, pt) => sum + (pt.value || 0), 0);
        });
        const backgroundColor = data.map((dataset) => dataset.color || getColor(0, cookie.get("color_scheme"), "odoo"));

        return {
            type: "doughnut",
            data: {
                labels: labels,
                datasets: [{
                    data: chartData,
                    backgroundColor: backgroundColor,
                    borderWidth: 1,
                }],
            },
            options: {
                plugins: {
                    legend: {
                        display: true,
                        position: 'right',
                        labels: {
                            usePointStyle: true,
                            boxWidth: 8,
                            padding: 10,
                            font: { size: 10 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                let label = context.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                let value = context.parsed;
                                let total = context.chart._metasets[context.datasetIndex].total;
                                let percentage = ((value / total) * 100).toFixed(1) + "%";
                                return label + value + ' (' + percentage + ')';
                            }
                        }
                    }
                },
                maintainAspectRatio: false,
                cutout: '60%', // Makes it a doughnut
            },
        };
    }
}

export const salesCatalogDashboardGraphField = {
    component: SalesCatalogDashboardGraphField,
    supportedTypes: ["text"],
    extractProps: ({ attrs }) => {
        return {
            graphType: attrs.graph_type,
        };
    },
};

registry.category("fields").add("sales_catalog_dashboard_graph", salesCatalogDashboardGraphField);
