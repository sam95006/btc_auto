/// Accessibility foundation for public mobile surfaces.
class A11ySettings {
  A11ySettings({
    this.textScale = 1.0,
    this.boldText = false,
    this.reduceMotion = false,
    this.screenReaderHints = true,
  });

  double textScale;
  bool boldText;
  bool reduceMotion;
  bool screenReaderHints;

  void setTextScale(double value) {
    textScale = value.clamp(0.85, 2.0);
  }
}
