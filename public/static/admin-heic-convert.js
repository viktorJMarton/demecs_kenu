// Client-side HEIC/HEIF -> JPEG conversion for admin uploads
// Uses `heic2any` (loaded from CDN). Converts selected .heic/.heif files
// to JPEG before they are uploaded and shows a small preview.

(function() {
    async function convertIfNeeded(file) {
        const name = (file.name || '').toLowerCase();
        const isHeic = name.endsWith('.heic') || name.endsWith('.heif') || (file.type && file.type.includes('heic'));
        if (!isHeic) return file;
        if (typeof heic2any !== 'function') {
            console.warn('heic2any not available, skipping client-side conversion');
            return file;
        }
        try {
            const converted = await heic2any({ blob: file, toType: 'image/jpeg', quality: 0.9 });
            // heic2any may return a Blob or an array of Blobs (for sequences)
            const blob = Array.isArray(converted) ? converted[0] : converted;
            const newName = file.name.replace(/\.(heic|heif)$/i, '.jpg');
            const newFile = new File([blob], newName, { type: 'image/jpeg', lastModified: file.lastModified });
            return newFile;
        } catch (err) {
            console.error('HEIC->JPEG conversion failed:', err);
            return file; // fallback to original
        }
    }

    function createPreviewContainer(input) {
        let container = input.parentElement.querySelector('.heic-preview-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'heic-preview-container mt-3 grid grid-cols-4 gap-2';
            input.parentElement.appendChild(container);
        }
        container.innerHTML = '';
        return container;
    }

    function addPreview(container, file) {
        const url = URL.createObjectURL(file);
        const wrap = document.createElement('div');
        wrap.className = 'rounded overflow-hidden border bg-base-100 p-1';
        wrap.style.height = '72px';
        wrap.style.width = '100%';
        const img = document.createElement('img');
        img.src = url;
        img.alt = file.name;
        img.style.width = '100%';
        img.style.height = '100%';
        img.style.objectFit = 'cover';
        wrap.appendChild(img);
        container.appendChild(wrap);
        // revoke url when image loads
        img.onload = () => URL.revokeObjectURL(url);
    }

    async function handleInputChange(e) {
        const input = e.currentTarget;
        if (!input || !input.files) return;
        const files = Array.from(input.files);
        if (!files.length) return;

        const dt = new DataTransfer();
        const previewContainer = createPreviewContainer(input);

        for (const f of files) {
            try {
                const out = await convertIfNeeded(f);
                dt.items.add(out);
                addPreview(previewContainer, out);
            } catch (err) {
                console.error('Error processing file', f.name, err);
                // fallback: add original
                dt.items.add(f);
                addPreview(previewContainer, f);
            }
        }

        // Assign the new FileList back to the input so the form will upload converted files
        try {
            input.files = dt.files;
        } catch (err) {
            console.warn('Could not assign converted files to input.files in this browser:', err);
        }
    }

    function init() {
        document.querySelectorAll('input[type="file"]').forEach(input => {
            // Only initialize inputs within the admin area (admin templates use body->container)
            // We simply attach to all file inputs; conversion will only run for HEIC files.
            input.addEventListener('change', handleInputChange);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
