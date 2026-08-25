import { render, screen } from "@testing-library/react";
import ProgressRing, { scoreTier } from "./ProgressRing";

describe("scoreTier", () => {
  test("classifies red below 60", () => {
    expect(scoreTier(0)).toBe("red");
    expect(scoreTier(59.9)).toBe("red");
  });

  test("classifies orange from 60 to 79.9", () => {
    expect(scoreTier(60)).toBe("orange");
    expect(scoreTier(79.9)).toBe("orange");
  });

  test("classifies green at 80 and above", () => {
    expect(scoreTier(80)).toBe("green");
    expect(scoreTier(100)).toBe("green");
  });

  test("classifies null/undefined as unknown", () => {
    expect(scoreTier(null)).toBe("unknown");
    expect(scoreTier(undefined)).toBe("unknown");
  });
});

test("renders the percentage and label", () => {
  render(<ProgressRing value={74.5} label="Final Score" />);
  expect(screen.getByText("74.5%")).toBeInTheDocument();
  expect(screen.getByText("Final Score")).toBeInTheDocument();
});

test("renders an em dash when value is null", () => {
  render(<ProgressRing value={null} label="Security" />);
  expect(screen.getByText("—")).toBeInTheDocument();
});

test("exposes the score tier as a data attribute for styling/testing", () => {
  const { container } = render(<ProgressRing value={90} label="Final Score" />);
  expect(container.querySelector('[data-tier="green"]')).toBeInTheDocument();
});
