import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";

afterEach(() => {
  window.localStorage.clear();
});
