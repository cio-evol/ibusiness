/** @odoo-module */

import { registry } from "@web/core/registry";
import { JournalDashboardGraphField } from "@web/views/fields/journal_dashboard_graph/journal_dashboard_graph_field";
import { getColor } from "@web/core/colors/colors";
import { cookie } from "@web/core/browser/cookie";

export class SalesCatalogDashboardGraphField extends JournalDashboardGraphField {
    static template = "web.JournalDashboardGraphField";

    getBarChartConfig() {
        // Collect all labels from all datasets to ensure x-axis is complete
        // In our case, all datasets should have the same labels (dates), but we should be robust.
        // However, standard Odoo dashboard graph usually assumes consistent x-axis or we just take the first one's labels if they are uniform.
        // Let's assume uniform labels from the first dataset for now as per Python generation.

        const labels = this.data[0].values.map(pt => pt.label);

        const datasets = this.data.map(dataset => {
            const data = dataset.values.map(pt => pt.value);
            // Use the color defined at the dataset level in Python
            const backgroundColor = dataset.color || getColor(0, cookie.get("color_scheme"), "odoo");

            return {
                label: dataset.key,
                data: data,
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
        // Aggregate data for Pie Chart: Sum of all values for each dataset (Status)
        const labels = this.data.map(dataset => dataset.key);
        const data = this.data.map(dataset => {
            return dataset.values.reduce((sum, pt) => sum + pt.value, 0);
        });
        const backgroundColor = this.data.map(dataset => dataset.color || getColor(0, cookie.get("color_scheme"), "odoo"));

        return {
            type: "doughnut", // or "pie"
            data: {
                labels: labels,
                datasets: [{
                    data: data,
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
    ...JournalDashboardGraphField,
    component: SalesCatalogDashboardGraphField,
    supportedTypes: ["text"],
    extractProps: ({ attrs }) => ({
        graphType: attrs.graph_type,
    }),
};

registry.category("fields").add("sales_catalog_dashboard_graph", salesCatalogDashboardGraphField);
