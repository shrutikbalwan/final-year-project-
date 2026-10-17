import 'package:flutter/material.dart';

Color statusColor(String value) {
  switch (value.toLowerCase()) {
    case 'connected':
    case 'normal':
    case 'acknowledged':
      return const Color(0xFF176B5B);
    case 'advisory':
    case 'intermittent':
      return const Color(0xFF8B5D00);
    case 'warning':
    case 'disconnected':
    case 'open':
      return const Color(0xFFAA4A00);
    case 'critical':
      return const Color(0xFFB42318);
    default:
      return Colors.blueGrey;
  }
}

class StatusBadge extends StatelessWidget {
  const StatusBadge({super.key, required this.label});
  final String label;
  @override
  Widget build(BuildContext context) {
    final color = statusColor(label);
    return Container(
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(30),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
          color: color,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}
