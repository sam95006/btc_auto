/// Accessibility foundation for public mobile surfaces (WCAG 2.2 AA oriented).
class A11ySettings {
  A11ySettings({
    this.textScale = 1.0,
    this.boldText = false,
    this.reduceMotion = false,
    this.screenReaderHints = true,
    this.highContrast = false,
  });

  /// Minimum interactive control size (logical pixels).
  static const double minTouchTarget = 44.0;

  double textScale;
  bool boldText;
  bool reduceMotion;
  bool screenReaderHints;
  bool highContrast;

  void setTextScale(double value) {
    textScale = value.clamp(0.85, 2.0);
  }

  /// Whether text scale approximates 200% zoom for layout stress.
  bool get isLargeText => textScale >= 1.9;
}
