import { describe, it, expect } from "vitest";
import {
  widthTier,
  defaultVoiceLibraryOpen,
  defaultControlPanelOpen,
  showNarrowBanner,
} from "./layout";

describe("widthTier", () => {
  it("classifies widths into tiers", () => {
    expect(widthTier(1600)).toBe("xl");
    expect(widthTier(1440)).toBe("xl");
    expect(widthTier(1300)).toBe("lg");
    expect(widthTier(1180)).toBe("lg");
    expect(widthTier(1100)).toBe("md");
    expect(widthTier(1024)).toBe("md");
    expect(widthTier(900)).toBe("sm");
  });
});

describe("panel defaults", () => {
  it("voice library open for xl/lg, collapsed for md/sm", () => {
    expect(defaultVoiceLibraryOpen(1440)).toBe(true);
    expect(defaultVoiceLibraryOpen(1200)).toBe(true);
    expect(defaultVoiceLibraryOpen(1100)).toBe(false);
    expect(defaultVoiceLibraryOpen(800)).toBe(false);
  });
  it("control panel open only for xl", () => {
    expect(defaultControlPanelOpen(1500)).toBe(true);
    expect(defaultControlPanelOpen(1300)).toBe(false);
    expect(defaultControlPanelOpen(1024)).toBe(false);
  });
});

describe("showNarrowBanner", () => {
  it("is true below 1024", () => {
    expect(showNarrowBanner(1023)).toBe(true);
    expect(showNarrowBanner(1024)).toBe(false);
    expect(showNarrowBanner(1400)).toBe(false);
  });
});
