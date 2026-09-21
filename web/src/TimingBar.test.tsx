import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { expect, test } from "vitest";
import { initialState } from "./reducer";
import { TimingBar } from "./TimingBar";

test("shows the SIMULATED badge from a health-seeded state with no spec event (F3)", () => {
  render(<TimingBar s={{ ...initialState, simulated: true }} />);
  expect(screen.getByTestId("simulated")).toHaveTextContent("SIMULATED");
});

test("hides the badge when simulated is false", () => {
  render(<TimingBar s={initialState} />);
  expect(screen.queryByTestId("simulated")).not.toBeInTheDocument();
});
