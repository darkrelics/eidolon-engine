import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../auth_state.dart';

class CharacterManagementScreen extends StatelessWidget {
  const CharacterManagementScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final authState = Provider.of<AuthState>(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Character Management',
          style: TextStyle(color: Colors.white),
        ),
        backgroundColor: Colors.black,
        automaticallyImplyLeading: false,
        actions: [
          IconButton(
            icon: const Icon(Icons.logout, color: Colors.white),
            onPressed: () async {
              await authState.signOut();
              if (context.mounted) {
                Navigator.of(context).pushReplacementNamed('/');
              }
            },
          ),
        ],
      ),
      body: Container(
        decoration: BoxDecoration(
          color: Colors.black,
          image: DecorationImage(
            image: const AssetImage('assets/background.jpg'),
            fit: BoxFit.cover,
            colorFilter: ColorFilter.mode(
              const Color.fromRGBO(0, 0, 0, 0.7), // Black with 0.7 opacity
              BlendMode.dstATop,
            ),
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.all(20.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Welcome, Adventurer',
                style: TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 30),
              const Text(
                'Character Management will be available soon.',
                style: TextStyle(fontSize: 16, color: Colors.white70),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 40),
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: const Color.fromRGBO(
                    255,
                    255,
                    255,
                    0.1,
                  ), // White with 0.1 opacity
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: Colors.white30),
                ),
                child: Column(
                  children: [
                    const Text(
                      'Character Creation Coming Soon',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'This feature will connect to AWS Lambda functions to manage character creation, stats, inventory, and progression within the Eidolon Engine world.',
                      style: TextStyle(fontSize: 14, color: Colors.white70),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 20),
                    ElevatedButton(
                      onPressed: null, // Disabled for now
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color.fromRGBO(
                          255,
                          255,
                          255,
                          0.3,
                        ), // White with 0.3 opacity
                        disabledBackgroundColor: const Color.fromRGBO(
                          255,
                          255,
                          255,
                          0.1,
                        ), // White with 0.1 opacity
                        disabledForegroundColor: const Color.fromRGBO(
                          255,
                          255,
                          255,
                          0.3,
                        ), // White with 0.3 opacity
                      ),
                      child: const Text('Create New Character'),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 40),
              const Center(
                child: Text(
                  'Stay tuned for updates!',
                  style: TextStyle(
                    fontSize: 14,
                    fontStyle: FontStyle.italic,
                    color: Colors.white60,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
