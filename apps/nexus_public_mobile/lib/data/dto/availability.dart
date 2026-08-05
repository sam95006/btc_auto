/// Public-safe availability markers for Decision Intelligence fields.
enum Availability {
  available,
  unavailable,
  stale,
  degraded,
  blocked,
}

Availability availabilityFrom(String? raw) {
  switch ((raw ?? '').toUpperCase()) {
    case 'AVAILABLE':
      return Availability.available;
    case 'STALE':
      return Availability.stale;
    case 'DEGRADED':
      return Availability.degraded;
    case 'BLOCKED':
      return Availability.blocked;
    case 'UNAVAILABLE':
    default:
      return Availability.unavailable;
  }
}

String availabilityToWire(Availability value) {
  switch (value) {
    case Availability.available:
      return 'AVAILABLE';
    case Availability.stale:
      return 'STALE';
    case Availability.degraded:
      return 'DEGRADED';
    case Availability.blocked:
      return 'BLOCKED';
    case Availability.unavailable:
      return 'UNAVAILABLE';
  }
}
