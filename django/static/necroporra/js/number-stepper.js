function initNumberStepper(root) {
  const input = root.querySelector('.js-number-stepper-input') || root.querySelector('input[type="number"]');
  const decrementButton = root.querySelector('[data-stepper-action="decrement"]');
  const incrementButton = root.querySelector('[data-stepper-action="increment"]');

  if (!input || !decrementButton || !incrementButton) {
    return;
  }

  const parseBound = (value) => {
    if (value === '' || value === null || value === undefined) {
      return null;
    }

    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };

  const minValue = parseBound(input.min);
  const maxValue = parseBound(input.max);
  const stepValue = (() => {
    const parsed = parseBound(input.step);
    return parsed && parsed > 0 ? parsed : 1;
  })();

  const clampValue = (value) => {
    let nextValue = value;

    if (minValue !== null) {
      nextValue = Math.max(minValue, nextValue);
    }
    if (maxValue !== null) {
      nextValue = Math.min(maxValue, nextValue);
    }

    return nextValue;
  };

  const getNumericValue = () => {
    const parsed = Number(input.value);
    return Number.isFinite(parsed) ? parsed : null;
  };

  const getFallbackValue = () => {
    if (minValue !== null) {
      return minValue;
    }
    if (maxValue !== null) {
      return maxValue;
    }
    return 0;
  };

  const updateAccessibility = (numericValue) => {
    input.setAttribute('role', 'spinbutton');

    if (minValue !== null) {
      input.setAttribute('aria-valuemin', String(minValue));
    }
    if (maxValue !== null) {
      input.setAttribute('aria-valuemax', String(maxValue));
    }

    if (numericValue !== null) {
      input.setAttribute('aria-valuenow', String(numericValue));
    } else {
      input.removeAttribute('aria-valuenow');
    }
  };

  const updateButtons = () => {
    const numericValue = getNumericValue();

    decrementButton.disabled = numericValue !== null && minValue !== null && numericValue <= minValue;
    incrementButton.disabled = numericValue !== null && maxValue !== null && numericValue >= maxValue;

    updateAccessibility(numericValue);
  };

  const setValue = (value) => {
    input.value = String(value);
    updateButtons();
  };

  const stepBy = (direction) => {
    const current = getNumericValue();
    const baseValue = current !== null ? current : getFallbackValue();
    const steppedValue = clampValue(baseValue + direction * stepValue);
    setValue(steppedValue);
  };

  decrementButton.addEventListener('click', () => {
    stepBy(-1);
  });

  incrementButton.addEventListener('click', () => {
    stepBy(1);
  });

  input.addEventListener('input', () => {
    updateButtons();
  });

  input.addEventListener('blur', () => {
    const current = getNumericValue();

    if (current === null) {
      setValue(getFallbackValue());
      return;
    }

    setValue(clampValue(current));
  });

  input.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      stepBy(1);
      return;
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      stepBy(-1);
    }
  });

  updateButtons();
}

function initNumberSteppers() {
  document.querySelectorAll('.js-number-stepper').forEach((stepper) => {
    initNumberStepper(stepper);
  });
}

window.initNumberStepper = initNumberStepper;
window.initNumberSteppers = initNumberSteppers;

document.addEventListener('DOMContentLoaded', initNumberSteppers);
