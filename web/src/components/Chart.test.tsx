import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, afterEach, expect, test, vi } from "vitest";
import embed from "vega-embed";
import { Chart } from "./Chart";
import { RowsContext } from "../rows";

vi.mock("vega-embed", () => ({ default: vi.fn() }));

const mockEmbed = embed as unknown as ReturnType<typeof vi.fn>;
const rows = [{ region: "EMEA", revenue: 10 }];

function Wrapped({ vega }: { vega: Record<string, unknown> }) {
  return (
    <RowsContext.Provider value={rows}>
      <Chart vega={vega} />
    </RowsContext.Provider>
  );
}

let renderedHandler: ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockEmbed.mockReset();
  renderedHandler = vi.fn();
  window.addEventListener("jevviz:rendered", renderedHandler as EventListener);
});

afterEach(() => {
  window.removeEventListener("jevviz:rendered", renderedHandler as EventListener);
});

test("shows an inline error and does not dispatch jevviz:rendered when embed rejects", async () => {
  mockEmbed.mockRejectedValueOnce(new Error("bad spec"));

  render(<Wrapped vega={{ mark: "bar" }} />);

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Chart failed to render: bad spec");
  expect(renderedHandler).not.toHaveBeenCalled();
});

test("finalizes a late-resolving view exactly once and skips the event when unmounted first", async () => {
  const finalize = vi.fn();
  let resolveEmbed: (value: { view: { finalize: () => void } }) => void = () => {};
  mockEmbed.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveEmbed = resolve;
      }),
  );

  const { unmount } = render(<Wrapped vega={{ mark: "bar" }} />);
  unmount();

  resolveEmbed({ view: { finalize } });
  await waitFor(() => expect(finalize).toHaveBeenCalledTimes(1));
  expect(renderedHandler).not.toHaveBeenCalled();
});

test("dispatches jevviz:rendered once with a numeric detail and embeds rows from context", async () => {
  mockEmbed.mockResolvedValueOnce({ view: { finalize: vi.fn() } });

  render(<Wrapped vega={{ mark: "bar" }} />);

  await waitFor(() => expect(renderedHandler).toHaveBeenCalledTimes(1));
  const event = renderedHandler.mock.calls[0][0] as CustomEvent<number>;
  expect(typeof event.detail).toBe("number");

  const [, specArg] = mockEmbed.mock.calls[0];
  expect((specArg as { datasets: { rows: unknown } }).datasets.rows).toBe(rows);
});
