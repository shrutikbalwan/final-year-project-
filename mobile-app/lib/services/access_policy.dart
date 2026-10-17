import 'session.dart';

bool canAcknowledgeIncident({
  required UserSession session,
  required bool serverEnforcesAuthorization,
}) =>
    serverEnforcesAuthorization &&
    session.isAuthenticated &&
    !session.isExpired &&
    (session.role == UserRole.supervisor || session.role == UserRole.administrator);
