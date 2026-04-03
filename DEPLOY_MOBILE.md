# 📱 Personal AI Mobile — Guia de Deploy do App Mobile (React Native + Expo)

> Versão 2.0.0 | React Native 0.76 | Expo SDK 52 | EAS Build

---

## 📋 Pré-requisitos

### Ambiente de Desenvolvimento

| Ferramenta    | Versão    | Instalar                              |
|---------------|-----------|---------------------------------------|
| Node.js       | ≥ 20 LTS  | https://nodejs.org                    |
| npm           | ≥ 10      | Incluído com Node                     |
| Expo CLI      | ≥ 10      | `npm i -g expo-cli`                   |
| EAS CLI       | ≥ 10      | `npm i -g eas-cli`                    |
| Git           | ≥ 2.40    | https://git-scm.com                   |

### Conta Expo (obrigatória para build)
1. Crie conta em https://expo.dev
2. Faça login: `eas login`
3. Vincule o projeto: `eas init`

### Para build iOS (opcional)
- macOS com Xcode 15+
- Apple Developer Account (US$99/ano)
- Certificados e provisioning profiles

### Para build Android
- Java 17+ (para build local)
- Android Studio (para emulador)
- Conta Google Play (US$25 único, para publicação)

---

## 🏃 Início Rápido — Desenvolvimento

```bash
# 1. Entre no diretório do app mobile
cd /opt/personal-ai/app/mobile   # ou: cd personal-ai-mobile/mobile

# 2. Instale dependências
npm install

# 3. Configure variáveis de ambiente
cp .env.example .env.local
# Edite .env.local:
echo "EXPO_PUBLIC_API_URL=https://seu-dominio.com" > .env.local

# 4. Inicie o servidor de desenvolvimento
npx expo start

# 5. Escaneie o QR code com o app Expo Go (iOS ou Android)
```

---

## 📱 Testando em Dispositivo Físico

### Expo Go (mais rápido, sem build)
```bash
# Instale o app "Expo Go" na App Store / Play Store
# Execute no terminal:
npx expo start --tunnel   # Para redes diferentes
npx expo start            # Para mesma rede WiFi
# Escaneie o QR code exibido
```

### Development Build (recomendado para funcionalidades nativas)
```bash
# Build para Android
eas build --platform android --profile development
# ou localmente:
npx expo run:android

# Build para iOS (requer macOS + Xcode)
eas build --platform ios --profile development
# ou localmente:
npx expo run:ios
```

---

## 🏗️ Build para Produção

### Android (APK / AAB)

#### Via EAS Build (cloud — recomendado)
```bash
cd mobile/

# Preview (APK para testes internos)
eas build --platform android --profile preview

# Produção (AAB para Google Play)
eas build --platform android --profile production
```

#### Build local (requer Java 17 + Android SDK)
```bash
cd mobile/
npx expo prebuild --platform android
cd android && ./gradlew assembleRelease
# APK em: android/app/build/outputs/apk/release/
```

### iOS (IPA)

#### Via EAS Build (cloud)
```bash
# Requer conta Apple Developer ativa
eas build --platform ios --profile production
```

#### Build local (somente macOS)
```bash
npx expo prebuild --platform ios
cd ios && xcodebuild -workspace PersonalAI.xcworkspace \
  -scheme PersonalAI -configuration Release \
  -archivePath PersonalAI.xcarchive archive
```

---

## ⚙️ Configuração de Variáveis de Ambiente

### .env.local (desenvolvimento)
```bash
EXPO_PUBLIC_API_URL=http://192.168.1.100:8765   # IP do servidor local
EXPO_PUBLIC_WS_URL=ws://192.168.1.100:8765
```

### Variáveis de produção no EAS
```bash
# Defina variáveis de ambiente no EAS (seguras, não no código)
eas env:create --name EXPO_PUBLIC_API_URL --value "https://seu-dominio.com" --environment production
eas env:create --name EXPO_PUBLIC_API_URL --value "https://preview.seu-dominio.com" --environment preview
```

### app.json — extra.apiUrl
Edite `mobile/app.json`:
```json
{
  "expo": {
    "extra": {
      "apiUrl": "https://seu-dominio.com",
      "eas": { "projectId": "SEU-EAS-PROJECT-ID" }
    }
  }
}
```

---

## 📤 Publicação nas Lojas

### Google Play Store

#### 1. Configure chave de serviço
```bash
# Baixe o google-play-service-account.json do Google Play Console
# Coloque em: mobile/google-play-service-account.json
```

#### 2. Primeiro envio (manual)
```bash
eas build --platform android --profile production
# Baixe o AAB e envie manualmente no Google Play Console
```

#### 3. Envios posteriores (automático)
```bash
eas submit --platform android
# Selecionará automaticamente o último build e enviará para Internal Testing
```

### Apple App Store

#### 1. Configure credenciais
```bash
eas credentials --platform ios
# Siga o wizard para criar/usar certificados
```

#### 2. Build e envio
```bash
eas build --platform ios --profile production
eas submit --platform ios
# Necessário configurar App Store Connect primeiro
```

---

## 🔄 OTA Updates (Over-the-Air)

Atualizações de JavaScript sem nova versão na loja:

```bash
# Publicar atualização OTA
eas update --branch production --message "Fix: melhorias na voz"

# Publicar para canal preview
eas update --branch preview --message "Nova feature: X"
```

> **Nota**: OTA não pode atualizar código nativo (Kotlin/Swift).
> Para alterações nativas, sempre faça novo build.

---

## 🗂️ Estrutura do Projeto Mobile

```
mobile/
├── app/                    # Expo Router (rotas de arquivo)
│   ├── _layout.tsx         # Layout raiz (inicialização)
│   ├── (tabs)/             # Navegação por abas
│   │   ├── _layout.tsx     # Layout das abas
│   │   ├── index.tsx       # Home
│   │   ├── chat.tsx        # Chat principal
│   │   ├── memory.tsx      # Memórias
│   │   ├── calendar.tsx    # Calendário
│   │   └── settings.tsx    # Configurações
│   └── +not-found.tsx
│
├── src/
│   ├── screens/            # Telas completas
│   │   ├── ChatScreen.tsx      # Chat + voz em tempo real
│   │   ├── HomeScreen.tsx      # Dashboard com status
│   │   ├── MemoryScreen.tsx    # Browser de memórias
│   │   ├── CalendarScreen.tsx  # Calendário CRUD
│   │   ├── RoutinesScreen.tsx  # Gerenciador de rotinas
│   │   ├── BluetoothScreen.tsx # Scan e conexão BT
│   │   ├── AppsScreen.tsx      # Apps e streaming
│   │   ├── MonitorScreen.tsx   # Monitor + auto-melhoria
│   │   └── SettingsScreen.tsx  # Configurações
│   │
│   ├── services/
│   │   └── api.ts          # Client API + WebSocket + offline queue
│   │
│   ├── store/
│   │   └── appStore.ts     # Estado global (Zustand + persistência)
│   │
│   ├── hooks/
│   │   └── useVoice.ts     # Captura de voz + TTS
│   │
│   ├── navigation/
│   │   └── AppNavigator.tsx # Navegação principal
│   │
│   └── components/         # Componentes reutilizáveis
│
├── assets/                 # Ícones e imagens
│   ├── icon.png            # Ícone do app (1024×1024)
│   ├── splash.png          # Splash screen (2048×2048)
│   └── adaptive-icon.png   # Ícone adaptativo Android
│
├── app.json                # Configuração Expo
├── eas.json                # Configuração EAS Build
├── package.json            # Dependências
└── tsconfig.json           # TypeScript
```

---

## 🔑 Funcionalidades e Permissões

| Funcionalidade        | iOS Permission                           | Android Permission            |
|-----------------------|------------------------------------------|-------------------------------|
| Microfone/Voz         | NSMicrophoneUsageDescription            | RECORD_AUDIO                  |
| Reconhecimento de fala| NSSpeechRecognitionUsageDescription     | —                             |
| Câmera                | NSCameraUsageDescription                | CAMERA                        |
| Contatos              | NSContactsUsageDescription              | READ/WRITE_CONTACTS           |
| Calendário            | NSCalendarsUsageDescription             | READ/WRITE_CALENDAR           |
| Bluetooth             | NSBluetoothAlwaysUsageDescription       | BLUETOOTH_CONNECT + SCAN      |
| Localização           | NSLocationWhenInUseUsageDescription     | ACCESS_FINE_LOCATION          |
| Ligações              | —                                       | CALL_PHONE                    |
| Background            | backgroundModes: audio, fetch           | RECEIVE_BOOT_COMPLETED        |

---

## 🌐 Modo Offline

O app funciona **completamente offline** com:

1. **SQLite local** (`expo-sqlite`): armazena mensagens e configurações
2. **Fila offline**: mensagens enviadas em offline são enfileiradas
3. **Sincronização automática**: quando volta online, envia todas as mensagens pendentes
4. **NetInfo**: detecta mudanças de conectividade em tempo real
5. **WebSocket reconnect**: reconecta automaticamente com backoff exponencial

```typescript
// Como funciona a fila offline (src/services/api.ts):
// 1. Verifica conectividade antes de cada request
// 2. Se offline: salva em SQLite local
// 3. Quando online: syncOfflineQueue() envia todos os itens pendentes
```

---

## 🎙️ Integração de Voz

### TTS (Text-to-Speech)
- **Primário**: API do servidor (edge-tts / OpenAI TTS)
- **Fallback**: expo-speech (nativo do dispositivo)

### STT (Speech-to-Text)
- **Primário**: API Whisper via servidor
- **Método**: Grava com expo-av → envia M4A → recebe transcrição

### Wake Word
- Configurável via `wakeWord` na store (padrão: "LAS")
- Para produção: integrar `react-native-voice` com modelo local Porcupine/Vosk

---

## 🔧 Diagnóstico e Debug

```bash
# Logs em tempo real
npx expo start --clear

# Limpar cache
npx expo start --clear
rm -rf node_modules && npm install

# Verificar build
eas build:view --latest

# TypeScript check
npx tsc --noEmit

# Lint
npx eslint . --ext .ts,.tsx
```

---

## 🚨 Problemas Comuns

### "Network request failed" 
- Verifique se o servidor backend está acessível
- Certifique-se que `EXPO_PUBLIC_API_URL` aponta para URL correta
- Para dev local, use o IP da máquina (não `localhost`)

### Microfone não funciona no iOS
- Verifique se `NSMicrophoneUsageDescription` está em `app.json`
- Aceite a permissão quando solicitado

### Bluetooth não encontra dispositivos
- Ative o Bluetooth no dispositivo
- Aceite as permissões de localização (necessárias para BT scan no Android)

### Build EAS falha
```bash
eas build:list  # Ver histórico de builds
eas diagnostics # Verificar configuração
```

### Atualização OTA não aplica
- Feche e abra o app
- Verifique o canal: `eas update:list`

---

## 📌 Links Úteis

- 📖 **Expo Docs**: https://docs.expo.dev
- 🏗️ **EAS Build**: https://docs.expo.dev/build/introduction
- 📦 **EAS Submit**: https://docs.expo.dev/submit/introduction
- 🔄 **EAS Update**: https://docs.expo.dev/eas-update/introduction
- 📱 **React Native Docs**: https://reactnative.dev/docs
- 🎙️ **expo-av (Áudio)**: https://docs.expo.dev/versions/latest/sdk/av
- 📡 **NetInfo**: https://github.com/react-native-netinfo/react-native-netinfo
