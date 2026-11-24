"use strict";
const test = require("node:test");
const assert = require("node:assert");
const { Cart } = require("../src/cart");

test("add and quantity", () => {
  const cart = new Cart();
  cart.add("pen", 2);
  cart.add("pen");
  assert.strictEqual(cart.quantity("pen"), 3);
});

test("rejects non-positive quantity", () => {
  assert.throws(() => new Cart().add("pen", 0), /quantity must be positive/);
});

test("total uses the price table", () => {
  const cart = new Cart();
  cart.add("pen", 2);
  cart.add("book");
  assert.strictEqual(cart.total({ pen: 150, book: 1200 }), 1500);
});

test("total needs a price for every line", () => {
  const cart = new Cart();
  cart.add("mug");
  assert.throws(() => cart.total({}), /no price for mug/);
});
