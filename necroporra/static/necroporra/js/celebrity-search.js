/**
 * Celebrity Search Module
 * Handles Wikidata search, results display, and celebrity picking
 */

let currentPoolSlug = '';
let selectedCelebrity = null;
let poolScoringMode = 'simple';
let remainingPredictions = 10;
let remainingWeight = 10;
let poolIsLocked = false;

function initCelebritySearch(poolSlug, poolId) {
    currentPoolSlug = poolSlug;
    
    // Get pool settings from global variables
    poolScoringMode = POOL_SCORING_MODE;
    if (typeof REMAINING_PREDICTIONS !== 'undefined') {
        remainingPredictions = REMAINING_PREDICTIONS;
    }
    if (typeof REMAINING_WEIGHT !== 'undefined') {
        remainingWeight = REMAINING_WEIGHT;
    }
    if (typeof POOL_IS_LOCKED !== 'undefined') {
        poolIsLocked = !!POOL_IS_LOCKED;
    }
    
    const addBtn = document.getElementById('addPredictionBtn');
    const cancelBtn = document.getElementById('cancelSearchBtn');
    const searchForm = document.getElementById('celebritySearchForm');
    const searchFormContainer = document.getElementById('searchForm');
    const predictionsListContainer = document.getElementById('predictionsList');
    
    if (!addBtn || !cancelBtn || !searchForm || !searchFormContainer || !predictionsListContainer) {
        initDeleteButtons();
        return;
    }

    // Show search form
    addBtn.addEventListener('click', () => {
        if (poolIsLocked) {
            showNotification('This pool is locked. You can no longer add predictions.', 'warning');
            return;
        }
        if (remainingPredictions <= 0) {
            showNotification('You have reached the maximum number of predictions for this pool', 'warning');
            return;
        }
        if (poolScoringMode === 'distributed' && remainingWeight <= 0) {
            showNotification('You have used your full bet budget of 10 points across your picks', 'warning');
            return;
        }
        searchFormContainer.style.display = 'block';
        predictionsListContainer.style.display = 'none';
        addBtn.style.display = 'none';
        document.getElementById('searchQuery').focus();
    });
    
    // Hide search form
    cancelBtn.addEventListener('click', () => {
        hideSearchForm();
    });
    
    // Handle search submission
    searchForm.addEventListener('submit', handleSearch);

    // Bind delete buttons for existing picks
    initDeleteButtons();
}

function hideSearchForm() {
    document.getElementById('searchForm').style.display = 'none';
    document.getElementById('predictionsList').style.display = 'block';
    document.getElementById('addPredictionBtn').style.display = 'inline-flex';
    document.getElementById('searchQuery').value = '';
    document.getElementById('searchResults').innerHTML = '';
    document.getElementById('searchError').style.display = 'none';
}

async function handleSearch(event) {
    event.preventDefault();
    
    const query = document.getElementById('searchQuery').value.trim();
    const searchResults = document.getElementById('searchResults');
    const searchError = document.getElementById('searchError');
    const searchBtn = document.getElementById('searchBtn');
    
    if (query.length < 2) {
        searchError.textContent = 'Please enter at least 2 characters';
        searchError.style.display = 'block';
        return;
    }
    
    searchError.style.display = 'none';
    searchResults.innerHTML = '<progress class="progress is-small is-info" max="100">Searching...</progress>';
    searchBtn.classList.add('is-loading');
    
    try {
        const data = await fetchWithCsrf(`/api/celebrities/search_wikidata/?q=${encodeURIComponent(query)}`, {
            method: 'GET',
        });
        
        renderSearchResults(data);
    } catch (error) {
        searchError.textContent = error.message || 'Search failed';
        searchError.style.display = 'block';
        searchResults.innerHTML = '';
    } finally {
        searchBtn.classList.remove('is-loading');
    }
}

function renderSearchResults(celebrities) {
    const searchResults = document.getElementById('searchResults');
    
    if (!celebrities || celebrities.length === 0) {
        searchResults.innerHTML = `
            <div class="notification is-warning is-light">
                <p class="has-text-centered">No celebrities found. Try a different search term.</p>
            </div>
        `;
        return;
    }
    
    const columns = document.createElement('div');
    columns.className = 'columns is-multiline';
    
    celebrities.forEach(celebrity => {
        const columnDiv = document.createElement('div');
        columnDiv.className = 'column is-half';
        
        const card = createCelebrityCard(celebrity);
        columnDiv.appendChild(card);
        columns.appendChild(columnDiv);
    });
    
    searchResults.innerHTML = '';
    searchResults.appendChild(columns);
}

function createCelebrityCard(celebrity) {
    const card = document.createElement('div');
    card.className = 'card celebrity-card';
    
    // Create image or placeholder
    let imageHtml = '';
    if (celebrity.image_url) {
        imageHtml = `
            <figure class="celebrity-image-container">
                <img src="${celebrity.image_url}" 
                     alt="${celebrity.name}" 
                     class="celebrity-image"
                     onerror="handleImageError(this, '${celebrity.name}')">
                <div class="celebrity-image-placeholder" style="display: none;">
                    ${getInitials(celebrity.name)}
                </div>
            </figure>
        `;
    } else {
        imageHtml = `
            <div class="celebrity-image-container">
                <div class="celebrity-image-placeholder">
                    ${getInitials(celebrity.name)}
                </div>
            </div>
        `;
    }
    
    const birthDate = celebrity.birth_date ? `<p class="subtitle is-7">Born: ${celebrity.birth_date}</p>` : '';
    const bio = celebrity.bio ? `<p class="content is-small">${celebrity.bio.substring(0, 100)}${celebrity.bio.length > 100 ? '...' : ''}</p>` : '';
    const isDeceased = !!celebrity.death_date;
    
    card.innerHTML = `
        ${imageHtml}
        <div class="card-content">
            <p class="title is-6">${celebrity.name}</p>
            ${birthDate}
            ${bio}
        </div>
        <footer class="card-footer">
            <a class="card-footer-item ${isDeceased ? 'has-text-grey-light is-static' : 'has-text-primary pick-celebrity-btn'}">
                <span class="icon"><i class="fas ${isDeceased ? 'fa-skull' : 'fa-hand-pointer'}"></i></span>
                <span>${isDeceased ? 'Dead' : 'Pick'}</span>
            </a>
        </footer>
    `;
    
    // Add click handler only for living celebrities
    if (!isDeceased) {
        const pickBtn = card.querySelector('.pick-celebrity-btn');
        pickBtn.addEventListener('click', (e) => {
            e.preventDefault();
            handleCelebrityPick(celebrity);
        });
    }
    
    return card;
}

function handleCelebrityPick(celebrity) {
    selectedCelebrity = celebrity;
    showConfirmModal(celebrity);
}

async function confirmPickCelebrity() {
    if (!selectedCelebrity) return;
    
    const confirmBtn = document.getElementById('confirmPickBtn');
    const originalBtnHtml = confirmBtn.innerHTML;
    confirmBtn.classList.add('is-loading');
    confirmBtn.disabled = true;
    
    // Get weight if in distributed scoring mode
    let weight = 1;
    if (poolScoringMode === 'distributed') {
        const weightInput = document.getElementById('predictionWeight');
        if (!weightInput) {
            showNotification('Could not find bet input for distributed scoring. Please reload and try again.', 'danger');
            confirmBtn.innerHTML = originalBtnHtml;
            confirmBtn.classList.remove('is-loading');
            confirmBtn.disabled = false;
            return;
        }

        weight = parseInt(weightInput.value, 10);

        if (Number.isNaN(weight)) {
            showNotification('Please enter a valid bet value', 'danger');
            confirmBtn.innerHTML = originalBtnHtml;
            confirmBtn.classList.remove('is-loading');
            confirmBtn.disabled = false;
            return;
        }

        // Validate weight
        if (weight < 1 || weight > 10) {
            showNotification('Weight must be between 1 and 10', 'danger');
            confirmBtn.innerHTML = originalBtnHtml;
            confirmBtn.classList.remove('is-loading');
            confirmBtn.disabled = false;
            return;
        }

        if (weight > remainingWeight) {
            showNotification(`You only have ${remainingWeight} weight points remaining`, 'danger');
            confirmBtn.innerHTML = originalBtnHtml;
            confirmBtn.classList.remove('is-loading');
            confirmBtn.disabled = false;
            return;
        }
    }
    
    try {
        // Step 1: Add celebrity to pool with weight
        const addCelebrityPayload = selectedCelebrity.wikidata_id 
            ? { wikidata_id: selectedCelebrity.wikidata_id, weight: weight }
            : { celebrity_id: selectedCelebrity.id, weight: weight };
        
        const response = await fetchWithCsrf(`/api/pools/${currentPoolSlug}/add_celebrity/`, {
            method: 'POST',
            body: JSON.stringify(addCelebrityPayload),
        });
        
        // Update remaining counts
        if (response.remaining_predictions !== undefined) {
            remainingPredictions = response.remaining_predictions;
        }
        if (response.remaining_weight !== undefined) {
            remainingWeight = response.remaining_weight;
        }
        
        // Success!
        hideModal();
        hideSearchForm();
        showNotification(`Successfully added ${selectedCelebrity.name} to your predictions!`, 'success');
        
        // Reload page to show new prediction
        setTimeout(() => {
            window.location.reload();
        }, 1500);
        
    } catch (error) {
        let errorMessage = error.message || 'Failed to add prediction';
        
        // Check for specific error messages
        if (errorMessage.includes('already exists') || errorMessage.includes('unique constraint') || errorMessage.includes('already predicted')) {
            errorMessage = "You've already predicted this celebrity in this pool.";
        } else if (errorMessage.includes('deceased')) {
            errorMessage = 'This celebrity is already deceased and cannot be picked.';
        } else if (errorMessage.includes('maximum') || errorMessage.includes('limit')) {
            errorMessage = error.message;
        } else if (errorMessage.includes('weight')) {
            errorMessage = error.message;
        }
        
        showNotification(errorMessage, 'danger');
        confirmBtn.innerHTML = originalBtnHtml;
        confirmBtn.classList.remove('is-loading');
        confirmBtn.disabled = false;
    }
}

// Make confirmPickCelebrity available globally for modal
window.confirmPickCelebrity = confirmPickCelebrity;


/**
 * Delete Pick Module
 * Handles deleting a user's own prediction from the pool
 */

function initDeleteButtons() {
    document.querySelectorAll('.delete-pick-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();

            if (btn.dataset.confirming === 'true') return;

            btn.dataset.confirming = 'true';
            const originalHtml = btn.innerHTML;
            btn.innerHTML = `
                <span class="is-size-7">Sure?</span>
                <button class="button is-danger is-small ml-1 confirm-yes-btn" type="button">Yes</button>
                <button class="button is-light is-small ml-1 confirm-no-btn" type="button">No</button>
            `;

            const predictionId = btn.getAttribute('data-prediction-id');

            btn.querySelector('.confirm-yes-btn').addEventListener('click', async (ev) => {
                ev.stopPropagation();
                await deletePick(predictionId, btn, originalHtml);
            });

            btn.querySelector('.confirm-no-btn').addEventListener('click', (ev) => {
                ev.stopPropagation();
                btn.dataset.confirming = 'false';
                btn.innerHTML = originalHtml;
            });
        });
    });
}

async function deletePick(predictionId, btn, originalBtnHtml) {
    if (poolIsLocked) {
        showNotification('This pool is locked. You can no longer edit predictions.', 'warning');
        btn.innerHTML = originalBtnHtml;
        btn.dataset.confirming = 'false';
        return;
    }

    const celebrityName = btn.getAttribute('data-celebrity-name') || 'pick';
    const card = btn.closest('.column');

    btn.innerHTML = '<span class="icon is-small"><i class="fas fa-spinner fa-pulse"></i></span><span>Deleting…</span>';

    try {
        const response = await fetchWithCsrf(
            `/api/pools/${currentPoolSlug}/predictions/${predictionId}/delete/`,
            { method: 'DELETE' }
        );

        // Update remaining counts
        if (response.remaining_predictions !== undefined) {
            remainingPredictions = response.remaining_predictions;
        }
        if (response.remaining_weight !== undefined) {
            remainingWeight = response.remaining_weight;
        }

        // Remove the card from DOM
        if (card) card.remove();

        showNotification(`Removed ${celebrityName} from your predictions.`, 'success');

        // If no predictions remain, show the empty state
        const predictionsList = document.getElementById('predictionsList');
        if (predictionsList) {
            const columns = predictionsList.querySelector('.columns');
            if (columns && columns.children.length === 0) {
                columns.remove();
                predictionsList.innerHTML = `
                    <div class="notification is-info is-light">
                        <p class="has-text-centered">
                            No predictions yet. Click "Add Prediction" to get started!
                        </p>
                    </div>
                `;
            }
        }

    } catch (error) {
        showNotification(error.message || 'Failed to delete prediction', 'danger');
        btn.innerHTML = originalBtnHtml;
    }
}