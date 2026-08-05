/// Runtime data mode for the public mobile client.
enum AppMode {
  mock,
  live;

  bool get isMock => this == AppMode.mock;
  bool get isLive => this == AppMode.live;

  static AppMode fromEnvironment() {
    const raw = String.fromEnvironment('NEXUS_APP_MODE', defaultValue: 'mock');
    switch (raw.toLowerCase()) {
      case 'live':
        return AppMode.live;
      case 'mock':
      default:
        return AppMode.mock;
    }
  }
}
