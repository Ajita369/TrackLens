document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const storeSelector = document.getElementById("store-selector");
    const dateInput = document.getElementById("date-input");
    
    // Metric Value Fields
    const valVisitors = document.getElementById("val-visitors");
    const valConversion = document.getElementById("val-conversion");
    const valQueue = document.getElementById("val-queue");
    const valAbandonment = document.getElementById("val-abandonment");
    
    // Card Containers for Animation
    const cardVisitors = document.getElementById("card-visitors");
    const cardConversion = document.getElementById("card-conversion");
    const cardQueue = document.getElementById("card-queue");
    const cardAbandonment = document.getElementById("card-abandonment");
    const iconConversion = document.getElementById("icon-conversion");
    const trendConversion = document.getElementById("trend-conversion");
    
    // Custom Containers
    const funnelContainer = document.getElementById("funnel-container");
    const heatmapContainer = document.getElementById("heatmap-container");
    const anomaliesContainer = document.getElementById("anomalies-container");
    const anomalyIndicator = document.getElementById("anomaly-indicator");
    
    // Banners & Footer Status
    const serviceUnavailableBanner = document.getElementById("service-unavailable-banner");
    const feedStatusBadge = document.getElementById("feed-status-badge");
    const feedStatusText = document.getElementById("feed-status-text");
    const lastEventTime = document.getElementById("last-event-time");
    const lastUpdatedText = document.getElementById("last-updated-text");
    
    let activeStore = "";
    let isServiceUnavailable = false;
    let pollIntervalId = null;

    // Helper to safely format decimal percentages
    function formatPct(val) {
        return (val * 100).toFixed(1) + "%";
    }

    // Helper to trigger pulse animation on updates
    function updateValueWithPulse(element, cardElement, newValue) {
        const oldValue = element.textContent;
        if (oldValue !== newValue) {
            element.textContent = newValue;
            cardElement.classList.add("update-pulse");
            setTimeout(() => {
                cardElement.classList.remove("update-pulse");
            }, 800);
        }
    }

    // Fetch /health on load to discover stores
    async function initializeDashboard() {
        try {
            const res = await fetch("/health");
            if (!res.ok) throw new Error("Health check failed");
            
            const data = await res.json();
            hideServiceBanner();
            
            const storeIds = Object.keys(data.stores);
            if (storeIds.length === 0) {
                storeSelector.innerHTML = '<option value="" disabled>No stores detected</option>';
                return;
            }
            
            // Populate select dropdown
            storeSelector.innerHTML = "";
            storeIds.forEach(storeId => {
                const opt = document.createElement("option");
                opt.value = storeId;
                opt.textContent = storeId;
                storeSelector.appendChild(opt);
            });
            
            activeStore = storeIds[0];
            
            // Try to set date input based on the latest event timestamp for this store
            const storeHealth = data.stores[activeStore];
            if (storeHealth && storeHealth.last_event_at) {
                const dateStr = storeHealth.last_event_at.split("T")[0];
                dateInput.value = dateStr;
            } else {
                // Default to UTC today
                dateInput.value = new Date().toISOString().split("T")[0];
            }
            
            // Set up event listeners
            storeSelector.addEventListener("change", (e) => {
                activeStore = e.target.value;
                // Auto update date input if health provides it for the newly selected store
                const newHealth = data.stores[activeStore];
                if (newHealth && newHealth.last_event_at) {
                    dateInput.value = newHealth.last_event_at.split("T")[0];
                }
                refreshDashboard();
            });
            
            dateInput.addEventListener("change", () => {
                refreshDashboard();
            });
            
            // Initial load & begin polling
            refreshDashboard();
            startPolling();
            
        } catch (err) {
            console.error("Initialization error:", err);
            showServiceBanner();
            // Retry initialisation after 3 seconds
            setTimeout(initializeDashboard, 3000);
        }
    }

    // Show/Hide Service Unavailable banner (503 handling)
    function showServiceBanner() {
        if (!isServiceUnavailable) {
            serviceUnavailableBanner.classList.remove("hidden");
            isServiceUnavailable = true;
        }
    }

    function hideServiceBanner() {
        if (isServiceUnavailable) {
            serviceUnavailableBanner.classList.add("hidden");
            isServiceUnavailable = false;
        }
    }

    // Polling controller
    function startPolling() {
        if (pollIntervalId) clearInterval(pollIntervalId);
        pollIntervalId = setInterval(refreshDashboard, 3000);
    }

    // Master update dashboard function
    async function refreshDashboard() {
        if (!activeStore) return;
        
        const date = dateInput.value;
        const queryParam = date ? `?date=${date}` : "";
        
        // 1. Fetch Health Status to update feed state
        fetchHealthStatus();
        
        // 2. Fetch Metrics
        fetchMetrics(queryParam);
        
        // 3. Fetch Funnel
        fetchFunnel(queryParam);
        
        // 4. Fetch Heatmap
        fetchHeatmap(queryParam);
        
        // 5. Fetch Anomalies
        fetchAnomalies(queryParam);
        
        // Update updated timestamp
        lastUpdatedText.textContent = `Last Updated: ${new Date().toLocaleTimeString()}`;
    }

    async function fetchHealthStatus() {
        try {
            const res = await fetch("/health");
            if (!res.ok) {
                if (res.status === 503) showServiceBanner();
                return;
            }
            hideServiceBanner();
            const data = await res.json();
            const storeInfo = data.stores[activeStore];
            
            if (storeInfo) {
                if (storeInfo.feed_status === "LIVE") {
                    feedStatusBadge.className = "feed-badge live";
                    feedStatusText.textContent = "LIVE";
                } else {
                    feedStatusBadge.className = "feed-badge stale";
                    feedStatusText.textContent = "STALE";
                }
                
                if (storeInfo.last_event_at) {
                    const dt = new Date(storeInfo.last_event_at);
                    lastEventTime.textContent = `Last Event: ${dt.toLocaleDateString()} ${dt.toLocaleTimeString()}`;
                } else {
                    lastEventTime.textContent = "No events ingested";
                }
            }
        } catch (err) {
            console.error("Health poll fail:", err);
        }
    }

    async function fetchMetrics(queryParam) {
        try {
            const res = await fetch(`/stores/${activeStore}/metrics${queryParam}`);
            if (!res.ok) {
                if (res.status === 503) showServiceBanner();
                return;
            }
            hideServiceBanner();
            const data = await res.json();
            
            // Unique Visitors
            updateValueWithPulse(valVisitors, cardVisitors, data.unique_visitors.toString());
            
            // Conversion Rate with Color Coding
            const convVal = data.conversion_rate;
            const convText = formatPct(convVal);
            updateValueWithPulse(valConversion, cardConversion, convText);
            
            // Style conversion metrics based on threshold rules
            iconConversion.className = "card-icon";
            if (convVal >= 0.50) {
                iconConversion.classList.add("green");
                trendConversion.className = "card-trend good";
                trendConversion.textContent = "High Conversion (>50%)";
            } else if (convVal >= 0.25) {
                iconConversion.classList.add("yellow");
                trendConversion.className = "card-trend average";
                trendConversion.textContent = "Average Conversion (>25%)";
            } else {
                iconConversion.classList.add("red");
                trendConversion.className = "card-trend poor";
                trendConversion.textContent = "Low Conversion (<25%)";
            }
            
            // Queue Depth
            updateValueWithPulse(valQueue, cardQueue, data.current_queue_depth.toString());
            
            // Abandonment Rate
            const abanText = formatPct(data.abandonment_rate);
            updateValueWithPulse(valAbandonment, cardAbandonment, abanText);
            
        } catch (err) {
            console.error("Metrics poll fail:", err);
        }
    }

    async function fetchFunnel(queryParam) {
        try {
            const res = await fetch(`/stores/${activeStore}/funnel${queryParam}`);
            if (!res.ok) return;
            const data = await res.json();
            
            if (!data.stages || data.stages.length === 0) {
                funnelContainer.innerHTML = '<div class="funnel-loading">No funnel data available for this date.</div>';
                return;
            }
            
            // Render Funnel Blocks
            funnelContainer.innerHTML = "";
            const funnelDiv = document.createElement("div");
            funnelDiv.className = "funnel-container";
            
            // Determine max count for calculating width percentages
            const maxCount = data.stages[0].count || 1;
            
            data.stages.forEach(stage => {
                const pctOfMax = maxCount > 0 ? (stage.count / maxCount) * 100 : 0;
                
                const stageDiv = document.createElement("div");
                stageDiv.className = "funnel-stage";
                stageDiv.innerHTML = `
                    <div class="funnel-stage-header">
                        <span>${stage.name}</span>
                        <span class="text-muted">${stage.count} visitors</span>
                    </div>
                    <div class="funnel-bar-wrapper">
                        <div class="funnel-bar-bg">
                            <div class="funnel-bar-fill" style="width: ${pctOfMax}%">
                                ${stage.count > 0 ? Math.round(pctOfMax) + "%" : ""}
                            </div>
                        </div>
                        <div class="funnel-dropoff ${stage.drop_off_pct > 0 ? 'active' : ''}">
                            ${stage.drop_off_pct > 0 ? '<i class="fa-solid fa-arrow-trend-down"></i> ' + stage.drop_off_pct.toFixed(1) + '%' : '—'}
                        </div>
                    </div>
                `;
                funnelDiv.appendChild(stageDiv);
            });
            funnelContainer.appendChild(funnelDiv);
            
        } catch (err) {
            console.error("Funnel poll fail:", err);
        }
    }

    async function fetchHeatmap(queryParam) {
        try {
            const res = await fetch(`/stores/${activeStore}/heatmap${queryParam}`);
            if (!res.ok) return;
            const data = await res.json();
            
            if (!data.zones || data.zones.length === 0) {
                heatmapContainer.innerHTML = '<div class="heatmap-loading">No traffic tracked in any zones.</div>';
                return;
            }
            
            heatmapContainer.innerHTML = "";
            data.zones.forEach(zone => {
                const row = document.createElement("div");
                row.className = `heatmap-row ${zone.data_confidence === 'low' ? 'heatmap-confidence-low' : ''}`;
                
                // Classify density intensity color scale
                let scaleClass = "density-scale-0";
                const score = zone.normalized_score;
                if (score >= 90) scaleClass = "density-scale-100";
                else if (score >= 70) scaleClass = "density-scale-80";
                else if (score >= 50) scaleClass = "density-scale-60";
                else if (score >= 30) scaleClass = "density-scale-40";
                else if (score >= 10) scaleClass = "density-scale-20";
                
                // Format Dwell ms to human readable seconds or minutes
                const dwellSeconds = zone.avg_dwell_ms / 1000;
                const dwellText = dwellSeconds >= 60 
                    ? `${(dwellSeconds / 60).toFixed(1)}m` 
                    : `${dwellSeconds.toFixed(0)}s`;
                
                row.innerHTML = `
                    <span class="zone-name">${zone.zone_id}</span>
                    <span class="zone-visits">${zone.visit_count}</span>
                    <span class="zone-dwell">${dwellText}</span>
                    <div class="heatmap-bar-bg">
                        <div class="heatmap-bar-fill ${scaleClass}" style="width: ${zone.normalized_score}%"></div>
                    </div>
                `;
                heatmapContainer.appendChild(row);
            });
            
        } catch (err) {
            console.error("Heatmap poll fail:", err);
        }
    }

    async function fetchAnomalies(queryParam) {
        try {
            const res = await fetch(`/stores/${activeStore}/anomalies${queryParam}`);
            if (!res.ok) return;
            const data = await res.json();
            
            // Check if queue spike is active for critical highlight
            const hasQueueSpike = data.anomalies.some(a => a.type === "QUEUE_SPIKE");
            if (hasQueueSpike) {
                cardQueue.classList.add("critical-queue");
            } else {
                cardQueue.classList.remove("critical-queue");
            }
            
            if (!data.anomalies || data.anomalies.length === 0) {
                anomalyIndicator.classList.remove("active");
                anomaliesContainer.innerHTML = `
                    <div class="anomalies-empty">
                        <i class="fa-solid fa-circle-check"></i>
                        <p>No operational anomalies detected. System running normal.</p>
                    </div>
                `;
                return;
            }
            
            // Alerts found, activate blinking badge
            anomalyIndicator.classList.add("active");
            anomaliesContainer.innerHTML = "";
            
            data.anomalies.forEach(anomaly => {
                const alertDiv = document.createElement("div");
                
                let sevClass = "info";
                let iconHtml = '<i class="fa-solid fa-circle-info"></i>';
                if (anomaly.severity === "CRITICAL") {
                    sevClass = "critical";
                    iconHtml = '<i class="fa-solid fa-triangle-exclamation"></i>';
                } else if (anomaly.severity === "WARN") {
                    sevClass = "warn";
                    iconHtml = '<i class="fa-solid fa-circle-exclamation"></i>';
                }
                
                alertDiv.className = `anomaly-alert ${sevClass}`;
                
                const timeText = anomaly.detected_at 
                    ? new Date(anomaly.detected_at).toLocaleTimeString() 
                    : "";
                
                alertDiv.innerHTML = `
                    <div class="anomaly-icon">${iconHtml}</div>
                    <div class="anomaly-content">
                        <h4>${anomaly.type.replace("_", " ")} <span class="anomaly-time">at ${timeText}</span></h4>
                        <p>${anomaly.details}</p>
                    </div>
                    <div class="anomaly-action">
                        <strong>Action: </strong>${anomaly.suggested_action}
                    </div>
                `;
                anomaliesContainer.appendChild(alertDiv);
            });
            
        } catch (err) {
            console.error("Anomalies poll fail:", err);
        }
    }

    // Run
    initializeDashboard();
});
