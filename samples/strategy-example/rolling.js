/**
 * Implementation of pandas.Series.rolling functionality for JavaScript arrays
 * 
 * This module provides functionality similar to pandas.Series.rolling in Python
 * for JavaScript arrays of float values.
 */

class Rolling {
  /**
   * Creates a rolling window object for a JavaScript array
   * @param {Array<number>} array - The input array of float values
   * @param {number} window - The size of the rolling window
   * @param {Object} options - Additional options
   * @param {number} [options.minPeriods=null] - Minimum number of observations required to have a value
   * @param {boolean} [options.center=false] - Set the labels at the center of the window
   * @param {boolean} [options.closed=null] - Make the interval closed on the 'right', 'left', 'both' or 'neither' endpoints
   */
  constructor(array, window, options = {}) {
    if (!Array.isArray(array)) {
      throw new Error('Input must be an array');
    }
    
    if (!Number.isInteger(window) || window <= 0) {
      throw new Error('Window size must be a positive integer');
    }
    
    this.array = array;
    this.window = window;
    this.minPeriods = options.minPeriods || 1;
    this.center = options.center || false;
    this.closed = options.closed || null;
    
    // Adjust the effective window size based on the 'closed' option
    this.effectiveWindow = this.window;
    if (this.closed === 'both') {
      this.effectiveWindow += 1;
    } else if (this.closed === 'neither' && this.window > 1) {
      this.effectiveWindow -= 1;
    }
  }
  
  /**
   * Get the window bounds for each position in the array
   * @returns {Array<{start: number, end: number}>} Array of window bounds
   * @private
   */
  _getWindowBounds() {
    const result = [];
    const n = this.array.length;
    
    for (let i = 0; i < n; i++) {
      let start, end;
      
      if (this.center) {
        const windowRadius = Math.floor(this.window / 2);
        start = Math.max(0, i - windowRadius);
        end = Math.min(n, i + this.window - windowRadius);
      } else {
        start = Math.max(0, i - this.window + 1);
        end = i + 1;
      }
      
      // Adjust based on closed parameter
      if (this.closed === 'left' && start > 0) {
        start -= 1;
      } else if (this.closed === 'right' && end < n) {
        end += 1;
      } else if (this.closed === 'both') {
        if (start > 0) start -= 1;
        if (end < n) end += 1;
      } else if (this.closed === 'neither') {
        if (start < i) start += 1;
        if (end > i + 1) end -= 1;
      }
      
      result.push({ start, end });
    }
    
    return result;
  }
  
  /**
   * Apply a function to each window
   * @param {Function} func - Function to apply to each window
   * @returns {Array<number>} Result of applying the function to each window
   * @private
   */
  _apply(func) {
    const result = new Array(this.array.length).fill(null);
    const bounds = this._getWindowBounds();
    
    for (let i = 0; i < this.array.length; i++) {
      const { start, end } = bounds[i];
      const windowValues = this.array.slice(start, end);
      
      // Check if we have enough observations
      if (windowValues.length >= this.minPeriods) {
        // Filter out NaN values
        const validValues = windowValues.filter(v => !isNaN(v));
        if (validValues.length >= this.minPeriods) {
          result[i] = func(validValues);
        }
      }
    }
    
    return result;
  }
  
  /**
   * Calculate the mean of values in each window
   * @returns {Array<number>} Array of mean values
   */
  mean() {
    return this._apply(values => {
      if (values.length === 0) return NaN;
      return values.reduce((sum, val) => sum + val, 0) / values.length;
    });
  }
  
  /**
   * Calculate the sum of values in each window
   * @returns {Array<number>} Array of sum values
   */
  sum() {
    return this._apply(values => {
      if (values.length === 0) return 0;
      return values.reduce((sum, val) => sum + val, 0);
    });
  }
  
  /**
   * Calculate the standard deviation of values in each window
   * @param {number} [ddof=1] - Delta degrees of freedom
   * @returns {Array<number>} Array of standard deviation values
   */
  std(ddof = 1) {
    return this._apply(values => {
      if (values.length <= ddof) return NaN;
      
      const mean = values.reduce((sum, val) => sum + val, 0) / values.length;
      const squaredDiffs = values.map(val => Math.pow(val - mean, 2));
      const variance = squaredDiffs.reduce((sum, val) => sum + val, 0) / (values.length - ddof);
      
      return Math.sqrt(variance);
    });
  }
  
  /**
   * Calculate the variance of values in each window
   * @param {number} [ddof=1] - Delta degrees of freedom
   * @returns {Array<number>} Array of variance values
   */
  var(ddof = 1) {
    return this._apply(values => {
      if (values.length <= ddof) return NaN;
      
      const mean = values.reduce((sum, val) => sum + val, 0) / values.length;
      const squaredDiffs = values.map(val => Math.pow(val - mean, 2));
      
      return squaredDiffs.reduce((sum, val) => sum + val, 0) / (values.length - ddof);
    });
  }
  
  /**
   * Calculate the minimum value in each window
   * @returns {Array<number>} Array of minimum values
   */
  min() {
    return this._apply(values => {
      if (values.length === 0) return NaN;
      return Math.min(...values);
    });
  }
  
  /**
   * Calculate the maximum value in each window
   * @returns {Array<number>} Array of maximum values
   */
  max() {
    return this._apply(values => {
      if (values.length === 0) return NaN;
      return Math.max(...values);
    });
  }
  
  /**
   * Calculate the median of values in each window
   * @returns {Array<number>} Array of median values
   */
  median() {
    return this._apply(values => {
      if (values.length === 0) return NaN;
      
      const sorted = [...values].sort((a, b) => a - b);
      const mid = Math.floor(sorted.length / 2);
      
      if (sorted.length % 2 === 0) {
        return (sorted[mid - 1] + sorted[mid]) / 2;
      } else {
        return sorted[mid];
      }
    });
  }
  
  /**
   * Count the number of non-NaN values in each window
   * @returns {Array<number>} Array of counts
   */
  count() {
    return this._apply(values => values.length);
  }
}

/**
 * Create a rolling window object for a JavaScript array
 * @param {Array<number>} array - The input array of float values
 * @param {number} window - The size of the rolling window
 * @param {Object} options - Additional options
 * @returns {Rolling} A Rolling object
 */
function rolling(array, window, options = {}) {
  return new Rolling(array, window, options);
}

// Export the rolling function
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { rolling };
} else {
  // For browser environments
  window.rolling = rolling;
}