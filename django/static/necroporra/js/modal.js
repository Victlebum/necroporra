/**
 * Modal Module
 * Handles celebrity confirmation modal
 */

function initModal() {
    const modal = document.getElementById('confirmModal');
    const closeBtn = document.getElementById('modalCloseBtn');
    const cancelBtn = document.getElementById('cancelPickBtn');
    const confirmBtn = document.getElementById('confirmPickBtn');
    const background = modal.querySelector('.modal-background');
    
    // Close handlers
    closeBtn.addEventListener('click', hideModal);
    cancelBtn.addEventListener('click', hideModal);
    background.addEventListener('click', hideModal);
    
    // Confirm handler
    confirmBtn.addEventListener('click', () => {
        if (window.confirmPickCelebrity) {
            window.confirmPickCelebrity();
        }
    });
    
    // ESC key handler
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.classList.contains('is-active')) {
            hideModal();
        }
    });
}

function showConfirmModal(celebrity) {
    const modal = document.getElementById('confirmModal');
    const modalContent = document.getElementById('modalContent');
    
    // Create image or placeholder
    let imageHtml = '';
    if (celebrity.image_url) {
        imageHtml = `
            <figure class="image is-3by4 mb-4" style="max-width: 300px; margin: 0 auto;">
                <img src="${celebrity.image_url}" 
                     alt="${celebrity.name}"
                     style="object-fit: cover; border-radius: 8px;"
                     onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                <div class="celebrity-image-placeholder" style="display: none; height: 400px; border-radius: 8px;">
                    ${getInitials(celebrity.name)}
                </div>
            </figure>
        `;
    } else {
        imageHtml = `
            <div class="celebrity-image-placeholder" style="height: 400px; max-width: 300px; margin: 0 auto; border-radius: 8px;">
                ${getInitials(celebrity.name)}
            </div>
        `;
    }
    
    const birthDateText = celebrity.birth_date_display || celebrity.birth_date;
    const deathDateText = celebrity.death_date_display || celebrity.death_date;
    const birthDate = birthDateText ? `<p><strong>Born:</strong> ${birthDateText}</p>` : '';
    const deathDate = deathDateText ? `<p><strong>Died:</strong> ${deathDateText}</p>` : '';
    const ageText = celebrity.age_display ? `<p><strong>${celebrity.age_display}</strong></p>` : '';
    const bio = celebrity.bio ? `<p class="content">${celebrity.bio}</p>` : '';
    
    // Add bet input for distributed scoring mode
    let weightInput = '';
    if (POOL_SCORING_MODE === 'distributed') {
        const maxWeight = typeof REMAINING_WEIGHT !== 'undefined' ? REMAINING_WEIGHT : 10;
        weightInput = `
            <div class="field mt-4">
                <label class="label">Bet (1\u2013${maxWeight})</label>
                <div class="control">
                    <div class="field has-addons number-stepper js-number-stepper">
                        <p class="control">
                            <button
                                type="button"
                                class="button number-stepper__button number-stepper__button--decrement js-number-stepper-button"
                                data-stepper-action="decrement"
                                aria-label="Decrease bet"
                            >
                                <span class="icon is-small" aria-hidden="true">
                                    <i class="fas fa-minus"></i>
                                </span>
                            </button>
                        </p>
                        <p class="control number-stepper__value-control">
                            <input
                                class="input number-stepper__input js-number-stepper-input"
                                type="number"
                                id="predictionWeight"
                                value="1"
                                min="1"
                                max="${maxWeight}"
                                step="1"
                                inputmode="numeric"
                                placeholder="Bet (1\u2013${maxWeight})"
                            >
                        </p>
                        <p class="control">
                            <button
                                type="button"
                                class="button number-stepper__button number-stepper__button--increment js-number-stepper-button"
                                data-stepper-action="increment"
                                aria-label="Increase bet"
                            >
                                <span class="icon is-small" aria-hidden="true">
                                    <i class="fas fa-plus"></i>
                                </span>
                            </button>
                        </p>
                    </div>
                </div>
                <p class="help">
                    <strong>Remaining bet budget:</strong> ${maxWeight} / 10<br>
                    Higher bet = more points if correct
                </p>
            </div>
        `;
    }
    
    modalContent.innerHTML = `
        ${imageHtml}
        <div class="content">
            <h3 class="title is-4 has-text-centered">${celebrity.name}</h3>
            ${birthDate}
            ${deathDate}
            ${ageText}
            ${bio}
            ${weightInput}
            <div class="notification is-info is-light mt-4">
                <p><strong>Are you sure you want to pick this celebrity?</strong></p>
                <p>This will add them to your predictions for this pool.</p>
            </div>
        </div>
    `;

    if (POOL_SCORING_MODE === 'distributed') {
        const modalStepper = modalContent.querySelector('.js-number-stepper');
        if (modalStepper && typeof window.initNumberStepper === 'function') {
            window.initNumberStepper(modalStepper);
        }
    }
    
    modal.classList.add('is-active');
    document.documentElement.classList.add('is-clipped');
}

function hideModal() {
    const modal = document.getElementById('confirmModal');
    modal.classList.remove('is-active');
    document.documentElement.classList.remove('is-clipped');
}

// Make functions available globally
window.showConfirmModal = showConfirmModal;
window.hideModal = hideModal;
