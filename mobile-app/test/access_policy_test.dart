import 'package:flutter_test/flutter_test.dart';
import 'package:smart_safety_helmet_mobile/services/access_policy.dart';
import 'package:smart_safety_helmet_mobile/services/session.dart';

void main() {
  test(
    'acknowledgement requires an unexpired supervisor and server enforcement',
    () {
      final supervisor = UserSession(
        userId: 'supervisor-01',
        role: UserRole.supervisor,
        expiresAt: DateTime.utc(2027),
        accessToken: 'token',
      );
      final viewer = UserSession(
        userId: 'viewer-01',
        role: UserRole.viewer,
        expiresAt: DateTime.utc(2027),
        accessToken: 'token',
      );
      final administrator = UserSession(
        userId: 'administrator-01',
        role: UserRole.administrator,
        expiresAt: DateTime.utc(2027),
        accessToken: 'token',
      );
      final expired = UserSession(
        userId: 'supervisor-01',
        role: UserRole.supervisor,
        expiresAt: DateTime.utc(2020),
        accessToken: 'expired',
      );
      final localPreview = UserSession(
        userId: 'local-viewer',
        role: UserRole.viewer,
        expiresAt: DateTime.utc(9999),
        development: true,
      );

      expect(
        canAcknowledgeIncident(
          session: supervisor,
          serverEnforcesAuthorization: true,
        ),
        isTrue,
      );
      expect(
        canAcknowledgeIncident(
          session: administrator,
          serverEnforcesAuthorization: true,
        ),
        isTrue,
      );
      expect(
        canAcknowledgeIncident(
          session: supervisor,
          serverEnforcesAuthorization: false,
        ),
        isFalse,
      );
      expect(
        canAcknowledgeIncident(
          session: viewer,
          serverEnforcesAuthorization: true,
        ),
        isFalse,
      );
      expect(
        canAcknowledgeIncident(
          session: expired,
          serverEnforcesAuthorization: true,
        ),
        isFalse,
      );
      expect(
        canAcknowledgeIncident(
          session: localPreview,
          serverEnforcesAuthorization: true,
        ),
        isFalse,
      );
    },
  );
}
