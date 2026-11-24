"use strict";

class Cart {
  constructor() {
    this.lines = new Map();
  }

  add(sku, quantity = 1) {
    if (!Number.isInteger(quantity) || quantity <= 0) {
      throw new Error("quantity must be positive");
    }
    this.lines.set(sku, (this.lines.get(sku) || 0) + quantity);
  }

  quantity(sku) {
    return this.lines.get(sku) || 0;
  }

  total(prices) {
    let sum = 0;
    for (const [sku, qty] of this.lines) {
      if (!(sku in prices)) throw new Error(`no price for ${sku}`);
      sum += prices[sku] * qty;
    }
    return sum;
  }
}

module.exports = { Cart };
