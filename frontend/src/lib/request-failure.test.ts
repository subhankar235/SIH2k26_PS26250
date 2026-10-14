import { test } from "node:test";
import assert from "node:assert/strict";
import { failureDetails } from "./request-failure.ts";
test("browser connection failures have a useful recovery message", () => {
  const result = failureDetails(new TypeError("Failed to fetch"));
  assert.equal(result.kind, "connection");
  assert.match(result.description, /make sure the service is running/);
  assert.doesNotMatch(result.description, /Failed to fetch/);
});
test("HTTP failures retain their status and distinguish recovery paths", () => {
  for (const [status, kind] of [
    [404, "missing"],
    [403, "access"],
    [429, "busy"],
    [503, "service"],
    [422, "input"],
  ] as const) {
    const result = failureDetails(
      Object.assign(new Error("Service message"), { status, code: "test" }),
    );
    assert.equal(result.kind, kind);
    assert.equal(result.status, status);
    assert.equal(result.technical, "Service message");
  }
});
test("validation messages remain available and unclassified failures get safe guidance", () => {
  assert.equal(
    failureDetails("Enter an integer seed.").description,
    "Enter an integer seed.",
  );
  assert.equal(
    failureDetails(new Error("Unexpected internal message")).kind,
    "request",
  );
  assert.doesNotMatch(
    failureDetails(new Error("Unexpected internal message")).description,
    /internal/,
  );
});
