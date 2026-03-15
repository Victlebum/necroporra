// Utility functions for necroporra

/**
 * Get CSRF token from cookie
 */
function getCsrfToken() {
  const name = 'csrftoken';
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

/**
 * Fetch wrapper that includes CSRF token
 */
async function fetchWithCsrf(url, options = {}) {
  const csrfToken = getCsrfToken();
  
  const defaultOptions = {
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    },
    credentials: 'same-origin',
  };
  
  const mergedOptions = {
    ...defaultOptions,
    ...options,
    headers: {
      ...defaultOptions.headers,
      ...options.headers,
    },
  };
  
  const response = await fetch(url, mergedOptions);
  
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.error || `HTTP ${response.status}`);
  }
  
  return response.json();
}

/**
 * Get initials from a name (for placeholder images)
 */
function getInitials(name) {
  return name
    .split(' ')
    .map(word => word[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

/**
 * Format date string to readable format
 */
function formatDate(dateString) {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', { 
    year: 'numeric', 
    month: 'long', 
    day: 'numeric' 
  });
}

/**
 * Show notification message
 */
function showNotification(message, type = 'info') {
  const notification = document.createElement('div');
  notification.className = `notification is-${type}`;
  notification.innerHTML = `
    <button class="delete"></button>
    <span>${message}</span>
  `;
  
  const container = document.getElementById('notification-container');
  if (container) {
    container.appendChild(notification);
    
    // Auto-remove after 7 seconds
    setTimeout(() => {
      notification.remove();
    }, 7000);
    
    // Remove on click
    notification.querySelector('.delete').addEventListener('click', () => {
      notification.remove();
    });
  }
}

/**
 * Handle image load error by showing placeholder
 */
function handleImageError(img, name) {
  img.style.display = 'none';
  const placeholder = img.nextElementSibling;
  if (placeholder) {
    placeholder.style.display = 'flex';
    if (name) {
      placeholder.textContent = getInitials(name);
    }
  }
}
