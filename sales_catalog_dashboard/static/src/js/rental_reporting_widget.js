/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState, onWillUpdateProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { loadJS } from "@web/core/assets";
import { rpc } from "@web/core/network/rpc";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class RentalReportingWidget extends Component {
    setup() {
        try {
            this.lineChartCanvasRef = useRef("lineChartCanvas");
            this.pieChartCanvasRef = useRef("pieChartCanvas");
            this.lineChart = null;
            this.pieChart = null;
            this.state = useState({
                loading: true,
                lineChartData: null,
                pieChartData: null,
                imageUrl: '',
                productName: '',
                productId: null,
            });
            
            // Poll for product changes when in graph view
            this.pollInterval = null;
            this.busListener = null;
        } catch (error) {
            console.error("Error in RentalReportingWidget setup:", error);
            this.state = useState({
                loading: false,
                lineChartData: null,
                pieChartData: null,
                imageUrl: '',
                productName: '',
                productId: null,
            });
        }

        onMounted(async () => {
            try {
                await this.loadChartJS();
                await this.loadChartData();
                this.startPolling();
                this.setupEventListeners();
            } catch (error) {
                console.error("Error in RentalReportingWidget setup:", error);
                this.state.loading = false;
            }
        });

        onWillUpdateProps(async (nextProps) => {
            const currentProductId = this.getProductId();
            const nextProductId = this.getProductId(nextProps);
            if (nextProductId !== currentProductId) {
                this.state.productId = nextProductId;
                await this.loadChartData(nextProductId);
            }
        });

        onWillUnmount(() => {
            this.stopPolling();
            // Remove event listener
            try {
                const env = this.props.env || this.env;
                if (env && env.bus && this.busListener) {
                    env.bus.removeEventListener('rental_reporting:product_changed', this.busListener);
                }
            } catch (error) {
                console.error("Error removing event listener:", error);
            }
            if (this.lineChart) {
                this.lineChart.destroy();
            }
            if (this.pieChart) {
                this.pieChart.destroy();
            }
        });
    }
    
    startPolling() {
        // Poll every 2 seconds to detect product changes from filters
        this.pollInterval = setInterval(async () => {
            const productId = this.getProductId();
            if (productId && productId !== this.state.productId) {
                this.state.productId = productId;
                await this.loadChartData(productId);
            }
        }, 2000);
    }
    
    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }
    
    setupEventListeners() {
        // Listen for product changes from graph controller
        try {
            const env = this.props.env || this.env;
            if (env && env.bus) {
                this.busListener = (ev) => {
                    const productId = ev.detail?.productId;
                    if (productId && productId !== this.state.productId) {
                        this.state.productId = productId;
                        this.loadChartData(productId);
                    }
                };
                env.bus.addEventListener('rental_reporting:product_changed', this.busListener);
            }
        } catch (error) {
            console.error("Error setting up event listeners:", error);
        }
    }

    getProductId(props = null) {
        try {
            const propsToUse = props || this.props;
            if (!propsToUse) {
                return null;
            }
            
            const record = propsToUse.record;
            const env = propsToUse.env || this.env;
            
            // Try to get product from record field
            const fieldName = propsToUse.options?.product_id_field || 'product_id';
            if (record && record.data && record.data[fieldName]) {
                const productField = record.data[fieldName];
                if (productField && productField.length > 0) {
                    return productField[0];
                }
            }
            
            // Try to get from search model domain
            if (env && env.searchModel) {
                const domain = env.searchModel.domain || [];
                // Check for product_id in domain
                for (const condition of domain) {
                    if (Array.isArray(condition) && condition.length >= 3) {
                        if (condition[0] === 'product_id' && condition[1] === '=') {
                            return condition[2];
                        }
                        if (condition[0] === 'product_id' && condition[1] === 'in' && Array.isArray(condition[2]) && condition[2].length > 0) {
                            return condition[2][0];
                        }
                    }
                }
            }
            
            // Try to get from active filters
            if (env && env.searchModel) {
                const activeFilters = env.searchModel.activeFilters || [];
                const productFilter = activeFilters.find(f => f && f.fieldName === 'product_id');
                if (productFilter && productFilter.value) {
                    return Array.isArray(productFilter.value) ? productFilter.value[0] : productFilter.value;
                }
                
                // Try to get from groupBy context
                const groupBy = env.searchModel.groupBy || [];
                const productGroup = groupBy.find(g => g && g.includes && g.includes('product_id'));
                if (productGroup) {
                    // If grouped by product, try to get from selection
                    const selectedRecords = env.searchModel.selectedRecords || [];
                    if (selectedRecords.length > 0) {
                        const firstRecord = selectedRecords[0];
                        if (firstRecord && firstRecord.data && firstRecord.data.product_id) {
                            const productField = firstRecord.data.product_id;
                            if (productField && productField.length > 0) {
                                return productField[0];
                            }
                        }
                    }
                }
            }
            
            // Try to get from view context
            if (env && env.config && env.config.context) {
                const context = env.config.context;
                if (context.search_default_product_id) {
                    return context.search_default_product_id;
                }
            }
        } catch (error) {
            console.error("Error getting product ID:", error);
        }
        
        return null;
    }

    async loadChartJS() {
        if (window.Chart) {
            return;
        }
        try {
            await loadJS('/web/static/lib/Chart/Chart.js');
            // Wait a bit for Chart.js to be fully loaded
            await new Promise(resolve => setTimeout(resolve, 100));
        } catch (error) {
            console.error("Error loading Chart.js:", error);
            // Try alternative path
            try {
                await loadJS('/web/static/lib/Chart.js/Chart.js');
            } catch (e) {
                console.error("Error loading Chart.js from alternative path:", e);
            }
        }
    }

    async loadChartData(productId = null) {
        const pid = productId || this.getProductId();
        if (!pid) {
            this.state.loading = false;
            this.state.lineChartData = null;
            this.state.pieChartData = null;
            this.state.imageUrl = '';
            this.state.productName = '';
            return;
        }

        try {
            this.state.loading = true;
            
            // Get date range from search model if available
            let dateFrom = null;
            let dateTo = null;
            const env = this.props.env || this.env;
            if (env && env.searchModel) {
                const domain = env.searchModel.domain || [];
                for (const condition of domain) {
                    if (Array.isArray(condition) && condition.length >= 3) {
                        if (condition[0] === 'date' && condition[1] === '>=') {
                            dateFrom = condition[2];
                        }
                        if (condition[0] === 'date' && condition[1] === '<=') {
                            dateTo = condition[2];
                        }
                    }
                }
            }
            
            const data = await rpc("/sales_catalog_dashboard/rental_reporting/chart_data", {
                product_id: pid,
                date_from: dateFrom,
                date_to: dateTo,
            });

            if (data.error) {
                console.error("Error loading chart data:", data.error);
                this.state.loading = false;
                return;
            }

            this.state.lineChartData = data.line_chart || null;
            this.state.pieChartData = data.pie_chart || null;
            this.state.imageUrl = data.product_info?.image_url || '';
            this.state.productName = data.product_info?.name || '';

            // Small delay to ensure canvas is ready
            setTimeout(() => {
                if (this.state.lineChartData) {
                    this.renderLineChart();
                }
                if (this.state.pieChartData) {
                    this.renderPieChart();
                }
            }, 100);
        } catch (error) {
            console.error("Error fetching chart data:", error);
        } finally {
            this.state.loading = false;
        }
    }

    renderLineChart() {
        if (!this.lineChartCanvasRef.el || !this.state.lineChartData) {
            return;
        }

        // Destroy existing chart
        if (this.lineChart) {
            try {
                this.lineChart.destroy();
            } catch (e) {
                console.error("Error destroying line chart:", e);
            }
            this.lineChart = null;
        }

        if (!window.Chart) {
            console.error("Chart.js not loaded");
            return;
        }

        try {
            const ctx = this.lineChartCanvasRef.el.getContext('2d');
            this.lineChart = new Chart(ctx, {
                type: 'line',
                data: this.state.lineChartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false,
                    },
                    plugins: {
                        legend: {
                            position: 'top',
                        },
                        title: {
                            display: true,
                            text: 'Rental Trends Over Time'
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const label = context.dataset.label || '';
                                    const value = context.parsed.y || 0;
                                    return `${label}: ${value.toFixed(2)}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            display: true,
                            title: {
                                display: true,
                                text: 'Date'
                            }
                        },
                        y: {
                            type: 'linear',
                            display: true,
                            position: 'left',
                            title: {
                                display: true,
                                text: 'Quantity'
                            }
                        },
                        y1: {
                            type: 'linear',
                            display: true,
                            position: 'right',
                            title: {
                                display: true,
                                text: 'Revenue'
                            },
                            grid: {
                                drawOnChartArea: false,
                            },
                        }
                    }
                }
            });
        } catch (error) {
            console.error("Error rendering line chart:", error);
        }
    }
    
    renderPieChart() {
        if (!this.pieChartCanvasRef.el || !this.state.pieChartData) {
            return;
        }

        // Destroy existing chart
        if (this.pieChart) {
            try {
                this.pieChart.destroy();
            } catch (e) {
                console.error("Error destroying pie chart:", e);
            }
            this.pieChart = null;
        }

        if (!window.Chart) {
            console.error("Chart.js not loaded");
            return;
        }

        try {
            const ctx = this.pieChartCanvasRef.el.getContext('2d');
            this.pieChart = new Chart(ctx, {
                type: 'pie',
                data: this.state.pieChartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                padding: 15,
                                usePointStyle: true,
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const label = context.label || '';
                                    const value = context.parsed || 0;
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                                    return `${label}: ${value.toFixed(2)} (${percentage}%)`;
                                }
                            }
                        }
                    }
                }
            });
        } catch (error) {
            console.error("Error rendering pie chart:", error);
        }
    }
}

RentalReportingWidget.template = "sales_catalog_dashboard.RentalReportingWidget";
RentalReportingWidget.props = {
    ...standardFieldProps,
    options: { type: Object, optional: true },
};

// Register as a field widget
registry.category("fields").add("rental_reporting_widget", {
    component: RentalReportingWidget,
    supportedOptions: [
        {
            label: "Product ID Field",
            name: "product_id_field",
            type: "string",
        },
    ],
    extractProps: ({ attrs }) => {
        return {
            options: attrs.options || {},
        };
    },
});

