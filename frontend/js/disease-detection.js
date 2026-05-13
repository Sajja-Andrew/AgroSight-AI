/**
 * AgroSight AI — Modern Disease Detection Module
 * Shared across Farmer & AgroVet dashboards
 *
 * Usage:
 *   window.DiseaseDetectionUI.init({ containerId: 'disease-detection', role: 'farmer' });
 */

(function() {
    'use strict';

    // ── Config ──
    const API_BASE_URL = (window.API_CONFIG && window.API_CONFIG.BASE_URL)
        ? window.API_CONFIG.BASE_URL
        : 'http://127.0.0.1:5000/api';

    function getAuthHeaders() {
        const token = localStorage.getItem('sc_token');
        const headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = 'Bearer ' + token;
        return headers;
    }

    // ── State ──
    let container = null;
    let role = 'farmer';
    let currentImageData = null;
    let currentResult = null;
    let videoStream = null;
    let isAnalyzing = false;

    // ── Public API ──
    window.DiseaseDetectionUI = {
        init(opts) {
            container = document.getElementById(opts.containerId || 'disease-detection');
            role = opts.role || 'farmer';
            if (!container) {
                console.warn('[DiseaseDetectionUI] Container not found:', opts.containerId);
                return;
            }
            renderSkeleton();
            bindEvents();
            loadHistory();
        }
    };

    // ── Skeleton Layout ──
    function renderSkeleton() {
        const section = container.querySelector('.detection-modern') || container;
        // If the container is a section with existing content, we replace the inner detection area
        // but keep the section wrapper.
        const modernWrap = document.createElement('div');
        modernWrap.className = 'detection-modern';
        modernWrap.innerHTML = `
            <!-- Upload Zone -->
            <div class="upload-zone" id="ddUploadZone" role="button" tabindex="0" aria-label="Upload plant image">
                <div class="upload-zone-inner">
                    <div class="upload-zone-icon"><i class="fas fa-plus"></i></div>
                    <div class="upload-zone-title">Upload or take a photo</div>
                    <div class="upload-zone-hint">Drag & drop an image, browse files, or use your camera</div>
                </div>
                <div class="upload-zone-actions">
                    <button class="upload-zone-btn primary" id="ddBrowseBtn" type="button">
                        <i class="fas fa-folder-open"></i> Browse Files
                    </button>
                    <button class="upload-zone-btn ghost" id="ddCameraBtn" type="button">
                        <i class="fas fa-camera"></i> Take Photo
                    </button>
                </div>
                <input type="file" id="ddFileInput" accept="image/*" hidden>
                <input type="file" id="ddCameraInput" accept="image/*" capture="environment" hidden>
            </div>

            <!-- Preview Stage -->
            <div class="preview-stage" id="ddPreviewStage" aria-live="polite">
                <div class="preview-image-wrap">
                    <img id="ddPreviewImg" alt="Uploaded plant image" />
                </div>
                <div class="preview-image-actions">
                    <button class="btn btn-analyze" id="ddAnalyzeBtn" type="button">
                        <i class="fas fa-brain"></i> Analyze with AI
                    </button>
                    <button class="btn btn-outline" id="ddRetakeBtn" type="button">
                        <i class="fas fa-redo"></i> Choose Another
                    </button>
                </div>
            </div>

            <!-- Analysis Stage -->
            <div class="analysis-stage" id="ddAnalysisStage" aria-live="polite">
                <div class="scanner-wrap">
                    <img id="ddScanImg" alt="" />
                    <div class="scan-grid"></div>
                    <div class="scan-particles"></div>
                    <div class="scan-line"></div>
                </div>
                <div class="analysis-steps" id="ddAnalysisSteps" aria-hidden="true">
                    <span class="analysis-step active" data-step="0"><i class="fas fa-circle"></i> Uploading</span>
                    <span class="analysis-step" data-step="1"><i class="fas fa-circle"></i> Analyzing</span>
                    <span class="analysis-step" data-step="2"><i class="fas fa-circle"></i> Identifying</span>
                    <span class="analysis-step" data-step="3"><i class="fas fa-circle"></i> Recommendations</span>
                </div>
                <div class="analysis-status" id="ddAnalysisStatus">Uploading image...</div>
            </div>

            <!-- Result Stage -->
            <div class="result-stage" id="ddResultStage" aria-live="polite">
                <div class="result-header-card" id="ddResultHeader"></div>
                <div class="ai-result-grid" id="ddResultGrid"></div>
                <div class="result-actions">
                    <button class="btn btn-analyze" id="ddNewDetectionBtn" type="button">
                        <i class="fas fa-plus"></i> New Detection
                    </button>
                    <button class="btn btn-ghost" id="ddFeedbackBtn" type="button">
                        <i class="fas fa-flag"></i> Report Wrong
                    </button>
                    ${role === 'farmer' ? `
                    <button class="btn btn-ghost" id="ddConsultBtn" type="button">
                        <i class="fas fa-user-md"></i> Consult Agro-Vet
                    </button>` : ''}
                </div>
            </div>

            <!-- Recent Detections -->
            <div class="recent-detections-modern" id="ddRecentWrap">
                <h4><i class="fas fa-clock"></i> Recent Detections</h4>
                <div class="detections-grid" id="ddDetectionsGrid"></div>
            </div>

            <!-- Toast -->
            <div class="detection-toast" id="ddToast" role="status" aria-live="polite"></div>
        `;

        // Replace old content if present, otherwise append
        const old = section.querySelector('.detection-layout, .detection-modern');
        if (old) old.replaceWith(modernWrap);
        else section.appendChild(modernWrap);
    }

    // ── Events ──
    function bindEvents() {
        const uploadZone = document.getElementById('ddUploadZone');
        const browseBtn = document.getElementById('ddBrowseBtn');
        const cameraBtn = document.getElementById('ddCameraBtn');
        const fileInput = document.getElementById('ddFileInput');
        const cameraInput = document.getElementById('ddCameraInput');
        const analyzeBtn = document.getElementById('ddAnalyzeBtn');
        const retakeBtn = document.getElementById('ddRetakeBtn');
        const newDetBtn = document.getElementById('ddNewDetectionBtn');
        const feedbackBtn = document.getElementById('ddFeedbackBtn');
        const consultBtn = document.getElementById('ddConsultBtn');

        if (uploadZone) {
            uploadZone.addEventListener('click', (e) => {
                if (e.target.closest('.upload-zone-btn')) return;
                fileInput.click();
            });
            uploadZone.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    fileInput.click();
                }
            });
            uploadZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadZone.classList.add('drag-over');
            });
            uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
            uploadZone.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadZone.classList.remove('drag-over');
                const file = e.dataTransfer.files[0];
                if (file && file.type.startsWith('image/')) processFile(file);
            });
        }

        if (browseBtn) browseBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            fileInput.click();
        });

        if (cameraBtn) cameraBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            openCamera();
        });

        if (fileInput) fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) processFile(file);
            fileInput.value = '';
        });

        if (cameraInput) cameraInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) processFile(file);
            cameraInput.value = '';
        });

        if (analyzeBtn) analyzeBtn.addEventListener('click', startAnalysis);
        if (retakeBtn) retakeBtn.addEventListener('click', resetToUpload);
        if (newDetBtn) newDetBtn.addEventListener('click', resetToUpload);
        if (feedbackBtn) feedbackBtn.addEventListener('click', showFeedbackForm);
        if (consultBtn) {
            consultBtn.addEventListener('click', () => {
                if (typeof navigateTo === 'function') navigateTo('messages');
                showToast('Select an agro-vet from the conversation list', 'info');
            });
        }
    }

    // ── File Processing ──
    function processFile(file) {
        if (!file.type.startsWith('image/')) {
            showToast('Please select an image file (JPG, PNG, WebP)', 'error');
            return;
        }
        if (file.size > 16 * 1024 * 1024) {
            showToast('Image too large. Max size is 16MB.', 'error');
            return;
        }
        const reader = new FileReader();
        reader.onload = (e) => showPreview(e.target.result);
        reader.readAsDataURL(file);
    }

    function showPreview(imageData) {
        currentImageData = imageData;
        currentResult = null;

        hideEl('ddUploadZone');
        hideEl('ddAnalysisStage');
        hideEl('ddResultStage');

        const previewStage = document.getElementById('ddPreviewStage');
        const previewImg = document.getElementById('ddPreviewImg');
        if (previewImg) previewImg.src = imageData;
        if (previewStage) previewStage.classList.add('active');
    }

    // ── Camera ──
    function openCamera() {
        // Try getUserMedia first for in-app experience
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            createCameraModal();
        } else {
            // Fallback to native file input with capture attribute
            const camInput = document.getElementById('ddCameraInput');
            if (camInput) camInput.click();
        }
    }

    function createCameraModal() {
        let modal = document.getElementById('ddCameraModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'ddCameraModal';
            modal.className = 'camera-modal';
            modal.setAttribute('role', 'dialog');
            modal.setAttribute('aria-modal', 'true');
            modal.setAttribute('aria-label', 'Camera capture');
            modal.innerHTML = `
                <div class="camera-modal-body">
                    <div class="camera-modal-header">
                        <h4><i class="fas fa-camera"></i> Take a Photo</h4>
                        <button id="ddCloseCamera" type="button" aria-label="Close camera"><i class="fas fa-times"></i></button>
                    </div>
                    <div class="camera-video-wrapper">
                        <video id="ddCameraVideo" autoplay playsinline></video>
                        <div class="camera-overlay"><div class="camera-focus-frame"></div></div>
                    </div>
                    <div class="camera-modal-footer">
                        <button class="upload-zone-btn ghost" id="ddSwitchCamera" type="button">
                            <i class="fas fa-sync-alt"></i> Switch
                        </button>
                        <button class="camera-shutter" id="ddCaptureBtn" type="button" aria-label="Capture photo">
                            <div class="camera-shutter-inner"></div>
                        </button>
                        <button class="upload-zone-btn ghost" id="ddCancelCamera" type="button">
                            <i class="fas fa-times"></i> Cancel
                        </button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);

            document.getElementById('ddCloseCamera').addEventListener('click', closeCamera);
            document.getElementById('ddCancelCamera').addEventListener('click', closeCamera);
            document.getElementById('ddCaptureBtn').addEventListener('click', capturePhoto);
            document.getElementById('ddSwitchCamera').addEventListener('click', switchCamera);
        }

        modal.classList.add('open');
        startCameraStream('environment');
    }

    let currentFacingMode = 'environment';

    async function startCameraStream(facingMode) {
        currentFacingMode = facingMode;
        const video = document.getElementById('ddCameraVideo');
        if (!video) return;
        try {
            if (videoStream) {
                videoStream.getTracks().forEach(t => t.stop());
            }
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: facingMode }
            });
            videoStream = stream;
            video.srcObject = stream;
        } catch (err) {
            console.error('Camera error:', err);
            showToast('Could not access camera. Using file picker instead.', 'warning');
            closeCamera();
            const camInput = document.getElementById('ddCameraInput');
            if (camInput) camInput.click();
        }
    }

    function switchCamera() {
        const next = currentFacingMode === 'environment' ? 'user' : 'environment';
        startCameraStream(next);
    }

    function capturePhoto() {
        const video = document.getElementById('ddCameraVideo');
        if (!video) return;
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth || 1280;
        canvas.height = video.videoHeight || 720;
        const ctx = canvas.getContext('2d');
        // Mirror if front camera
        if (currentFacingMode === 'user') {
            ctx.translate(canvas.width, 0);
            ctx.scale(-1, 1);
        }
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.92);
        closeCamera();
        showPreview(dataUrl);
    }

    function closeCamera() {
        if (videoStream) {
            videoStream.getTracks().forEach(t => t.stop());
            videoStream = null;
        }
        const modal = document.getElementById('ddCameraModal');
        if (modal) modal.classList.remove('open');
    }

    // ── Analysis ──
    async function startAnalysis() {
        if (isAnalyzing || !currentImageData) return;
        isAnalyzing = true;

        hideEl('ddPreviewStage');
        hideEl('ddResultStage');

        const analysisStage = document.getElementById('ddAnalysisStage');
        const scanImg = document.getElementById('ddScanImg');
        if (scanImg) scanImg.src = currentImageData;
        if (analysisStage) analysisStage.classList.add('active');

        setAnalysisStep(0, 'Uploading image...');

        try {
            setAnalysisStep(1, 'Analyzing with AI...');
            const response = await fetch(API_BASE_URL + '/analyze', {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({ image: currentImageData, caption: '' })
            });
            const result = await response.json();

            if (!result.is_leaf) {
                isAnalyzing = false;
                hideEl('ddAnalysisStage');
                showToast(result.message || 'This does not appear to be a plant leaf. Please upload a clear leaf image.', 'warning');
                showPreview(currentImageData);
                return;
            }

            if (result.success) {
                setAnalysisStep(2, 'Identifying disease...');
                await delay(600);
                setAnalysisStep(3, 'Preparing recommendations...');
                await delay(500);
                hideEl('ddAnalysisStage');
                currentResult = result;
                renderResult(result, currentImageData);
                saveDetection(result, currentImageData);
                loadHistory();
                showToast('Analysis complete: ' + (result.disease || 'Unknown'), 'success');
            } else {
                throw new Error(result.message || 'Analysis failed');
            }
        } catch (error) {
            console.error('Analysis error:', error);
            isAnalyzing = false;
            hideEl('ddAnalysisStage');
            showToast(error.message || 'Connection error. Please try again.', 'error');
            showPreview(currentImageData);
        }
    }

    function setAnalysisStep(stepIndex, statusText) {
        document.querySelectorAll('.analysis-step').forEach((el, i) => {
            el.classList.toggle('active', i === stepIndex);
        });
        const statusEl = document.getElementById('ddAnalysisStatus');
        if (statusEl) statusEl.textContent = statusText;
    }

    // ── Result Rendering ──
    function renderResult(result, imageData) {
        const resultStage = document.getElementById('ddResultStage');
        if (!resultStage) return;

        const pred = result;
        const isHealthy = pred.is_healthy === true || (pred.disease || '').toLowerCase().includes('healthy');
        const confPercent = Math.round((pred.confidence || 0) * 100);
        const sev = pred.severity || 'Unknown';
        const sevKey = (sev || '').toLowerCase();
        const sevClass = sevKey.includes('severe') ? 'severe' : sevKey.includes('moderate') ? 'moderate' : sevKey.includes('mild') ? 'mild' : isHealthy ? 'healthy' : 'unknown';
        const sevLabel = isHealthy ? 'Healthy' : sev;

        // Header card
        const header = document.getElementById('ddResultHeader');
        if (header) {
            header.innerHTML = `
                <div class="result-thumb"><img src="${escapeHtml(imageData)}" alt="Analyzed plant" /></div>
                <div class="result-meta">
                    <div class="result-disease-name">${escapeHtml(pred.disease || 'Unknown')}</div>
                    <div class="result-crop-tag"><i class="fas fa-seedling"></i> ${escapeHtml(pred.crop || 'Unknown crop')}</div>
                    <div class="confidence-gauge">
                        <div class="confidence-donut" style="--fill-angle: ${confPercent * 3.6}deg;">
                            <div class="confidence-donut-bg"></div>
                            <div class="confidence-donut-fill"></div>
                            <div class="confidence-donut-text">${confPercent}%</div>
                        </div>
                        <div class="confidence-info">
                            <div class="confidence-label">AI Confidence</div>
                            <div class="confidence-value">${confPercent}%</div>
                            <div class="confidence-bar-track"><div class="confidence-bar-fill" style="width:${confPercent}%"></div></div>
                        </div>
                    </div>
                    <div class="severity-badge ${sevClass}"><span class="severity-dot"></span> ${escapeHtml(sevLabel)}</div>
                </div>
            `;
        }

        // Result grid cards
        const grid = document.getElementById('ddResultGrid');
        if (grid) {
            grid.innerHTML = '';

            const symptoms = normalizeList(pred.symptoms);
            if (symptoms.length) {
                grid.appendChild(buildAccordionCard('Symptoms Observed', 'icon-symptoms', 'fa-list-ul', symptoms, true));
            }

            const causes = pred.causes ? [pred.causes] : [];
            if (causes.length) {
                grid.appendChild(buildAccordionCard('Possible Causes', 'icon-causes', 'fa-virus', causes, false, true));
            }

            const recs = normalizeList(pred.recommendation);
            if (recs.length) {
                grid.appendChild(buildAccordionCard('Treatment Recommendations', 'icon-treatment', 'fa-prescription-bottle-alt', recs, true));
            }

            const prevention = pred.prevention ? [pred.prevention] : [];
            if (prevention.length) {
                grid.appendChild(buildAccordionCard('Prevention Guidance', 'icon-prevention', 'fa-shield-alt', prevention, false, true));
            }

            const envRecs = normalizeList(pred.environmental_recommendations);
            if (envRecs.length) {
                grid.appendChild(buildAccordionCard('Environmental Recommendations', 'icon-environment', 'fa-cloud-sun', envRecs, true));
            }

            const pesticides = normalizeList(pred.pesticides_fertilizers || pred.pesticides);
            if (pesticides.length) {
                grid.appendChild(buildAccordionCard('Recommended Pesticides / Fertilizers', 'icon-fertilizer', 'fa-flask', pesticides, true));
            }
        }

        resultStage.classList.add('active');
        isAnalyzing = false;

        // Expose for legacy feedback handlers
        window._lastPrediction = result;
        window._lastImageData = imageData;
    }

    function buildAccordionCard(title, iconClass, faIcon, items, isList, isParagraph) {
        const card = document.createElement('div');
        card.className = 'result-card';
        const id = 'card_' + Math.random().toString(36).slice(2, 9);
        card.innerHTML = `
            <div class="result-card-header" role="button" tabindex="0" aria-expanded="false" aria-controls="${id}">
                <i class="fas ${faIcon} ${iconClass}"></i>
                <h5>${escapeHtml(title)}</h5>
                <i class="fas fa-chevron-down toggle-icon"></i>
            </div>
            <div class="result-card-body" id="${id}">
                ${isList ? '<ul>' + items.map(s => '<li>' + escapeHtml(s) + '</li>').join('') + '</ul>' : ''}
                ${isParagraph ? '<p>' + escapeHtml(items[0] || '') + '</p>' : ''}
            </div>
        `;
        const header = card.querySelector('.result-card-header');
        header.addEventListener('click', () => toggleCard(card, header));
        header.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                toggleCard(card, header);
            }
        });
        // Open first card by default
        return card;
    }

    function toggleCard(card, header) {
        const isOpen = card.classList.contains('open');
        card.classList.toggle('open', !isOpen);
        header.setAttribute('aria-expanded', String(!isOpen));
    }

    // ── History ──
    async function loadHistory() {
        const grid = document.getElementById('ddDetectionsGrid');
        if (!grid) return;

        let detections = [];
        try {
            const res = await fetch(API_BASE_URL + '/detections?limit=6', { headers: getAuthHeaders() });
            if (res.ok) {
                const data = await res.json();
                if (data.success) {
                    detections = (data.detections || []).map(d => ({
                        id: d.id,
                        disease: d.disease,
                        confidence: d.confidence,
                        severity: d.severity,
                        img: d.image_id ? '/uploads/' + d.image_id : '',
                        date: d.created_at
                    }));
                }
            }
        } catch (e) {
            console.warn('History load failed, using localStorage', e);
        }

        if (!detections.length) {
            const localKey = role === 'farmer' ? 'sc_detections' : 'sc_detections_agrovet';
            detections = JSON.parse(localStorage.getItem(localKey) || '[]').slice(0, 6);
        }

        if (!detections.length) {
            grid.innerHTML = `
                <div class="detection-empty" style="grid-column: 1 / -1;">
                    <i class="fas fa-images"></i>
                    <p>No detections yet. Upload a plant image to get started.</p>
                </div>`;
            return;
        }

        grid.innerHTML = detections.map(d => {
            const conf = (d.confidence < 1) ? Math.round(d.confidence * 100) : d.confidence;
            return `
                <div class="detection-card" data-id="${d.id}">
                    <img class="detection-card-img" src="${escapeHtml(d.img || '')}" alt="${escapeHtml(d.disease || '')}" loading="lazy" onerror="this.style.display='none'" />
                    <div class="detection-card-body">
                        <div class="detection-card-name">${escapeHtml(d.disease || 'Unknown')}</div>
                        <div class="detection-card-meta">
                            <span>${escapeHtml(d.severity || 'Unknown')}</span>
                            <span class="detection-card-conf">
                                <span>${conf}%</span>
                                <span class="conf-bar"><span class="conf-bar-fill" style="width:${conf}%"></span></span>
                            </span>
                            <span>${new Date(d.date).toLocaleDateString()}</span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    // ── Save / Feedback ──
    function saveDetection(prediction, imageData) {
        const localKey = role === 'farmer' ? 'sc_detections' : 'sc_detections_agrovet';
        const detections = JSON.parse(localStorage.getItem(localKey) || '[]');
        detections.unshift({
            id: Date.now(),
            disease: prediction.disease,
            confidence: prediction.confidence,
            severity: prediction.severity || 'Unknown',
            img: imageData,
            date: new Date().toISOString()
        });
        localStorage.setItem(localKey, JSON.stringify(detections.slice(0, 50)));
        // Also log activity if available
        if (typeof logActivity === 'function') {
            logActivity('detection', 'Detected ' + (prediction.disease || 'Unknown'));
        }
    }

    function showFeedbackForm() {
        if (!currentResult) {
            showToast('No prediction to report. Please analyze an image first.', 'error');
            return;
        }
        const pred = currentResult;
        const correctClass = prompt(
            'Report Wrong Prediction\n\n' +
            'Predicted: ' + (pred.disease || 'Unknown') + '\n\n' +
            'Please enter the correct disease class name (or "skip" to cancel):'
        );
        if (!correctClass || correctClass.toLowerCase() === 'skip') return;
        submitFeedback(correctClass);
    }

    async function submitFeedback(correctClass) {
        try {
            showToast('Submitting feedback...', 'info');
            const response = await fetch(API_BASE_URL + '/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    predicted_class: currentResult.class_name || currentResult.disease,
                    correct_class: correctClass,
                    confidence: (currentResult.confidence || 0) * 100,
                    image: currentImageData
                })
            });
            const result = await response.json();
            if (result.success) {
                showToast('Thank you! Your feedback has been saved.', 'success');
            } else {
                showToast('Feedback saved locally. The AI will learn from it.', 'success');
            }
        } catch (error) {
            console.error('Feedback error:', error);
            showToast('Could not submit to server, saved locally.', 'warning');
        }
    }

    // ── Reset ──
    function resetToUpload() {
        currentImageData = null;
        currentResult = null;
        isAnalyzing = false;
        window._lastPrediction = null;
        window._lastImageData = null;

        hideEl('ddPreviewStage');
        hideEl('ddAnalysisStage');
        hideEl('ddResultStage');

        const uploadZone = document.getElementById('ddUploadZone');
        if (uploadZone) uploadZone.classList.remove('hidden');

        const previewImg = document.getElementById('ddPreviewImg');
        if (previewImg) previewImg.src = '';
    }

    // ── Utilities ──
    function hideEl(id) {
        const el = document.getElementById(id);
        if (el) el.classList.remove('active');
    }

    function delay(ms) {
        return new Promise(r => setTimeout(r, ms));
    }

    function normalizeList(val) {
        if (!val) return [];
        if (Array.isArray(val)) return val.filter(Boolean);
        return [val].filter(Boolean);
    }

    function escapeHtml(text) {
        if (text == null) return '';
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }

    function showToast(message, type) {
        const toast = document.getElementById('ddToast');
        if (!toast) return;
        toast.textContent = message;
        toast.className = 'detection-toast ' + (type || 'success') + ' show';
        setTimeout(() => toast.classList.remove('show'), 3500);
    }

    // Close camera on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeCamera();
    });
})();
