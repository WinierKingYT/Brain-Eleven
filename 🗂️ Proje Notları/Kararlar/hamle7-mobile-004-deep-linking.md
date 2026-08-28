---
type: decision
title: Deep Linking with Deferred Deep Links
category: Mobile Development & Navigation
status: active
created: 2026-08-28
source: mobile-production-systems (Hamle 7)
tags: [mobile, deep-linking, navigation, routing, app-links]
---

# Deep Linking & Deferred Deep Links

**Pattern:** Opening specific app screens via URL/QR codes with graceful fallback if app uninstalled.

## The Problem

Marketing campaigns need to deep link:
- QR code → specific product detail screen
- App not installed yet → should redirect to store
- App installed → open direct to product

Without proper handling:
- Link opens wrong screen or crashes
- No fallback to app store
- Deferred deep links (links saved before install) lost

## Solution: Firebase Dynamic Links (Deferred) or App Links

**Firebase Dynamic Links (Simple & Powerful)**

```swift
// iOS: Handle deferred deep links after install
func application(
  _ application: UIApplication,
  didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
) -> Bool {
  DynamicLinks.dynamicLinks().handleUniversalLink(
    launchOptions?[UIApplication.LaunchOptionsKey.url] as? URL
  ) { dynamicLink, error in
    if let deepLink = dynamicLink?.url {
      // App was installed; handle deep link
      handleDeepLink(deepLink)
    } else if error != nil {
      // App not installed; Firebase redirects to App Store
      // No action needed; OS handles redirect
    }
  }
  return true
}

// Create dynamic link
func createDynamicLink(product_id: String) -> String {
  let linkBuilder = DynamicLinkComponents(
    link: URL(string: "https://myapp.com/products/\(product_id)")!,
    domainURIPrefix: "https://myapp.page.link"
  )!
  
  linkBuilder.iOSParameters = DynamicLinkIOSParameters(bundleID: "com.myapp")
  linkBuilder.iOSParameters?.appStoreID = "1234567890"
  linkBuilder.socialMetaTagParameters = DynamicLinkSocialMetaTagParameters()
  linkBuilder.socialMetaTagParameters?.title = "Check out this product!"
  linkBuilder.socialMetaTagParameters?.descriptionText = "Amazing deals"
  
  return linkBuilder.url?.absoluteString ?? ""
}
```

**App Links (Android) / Universal Links (iOS) Standard**

```
1. User clicks: https://myapp.com/products/123

2. OS checks for app association file (/.well-known/assetlinks.json):
   [
     {
       "relation": ["delegate_permission/common.handle_urls"],
       "target": {
         "namespace": "android_app",
         "package_name": "com.myapp",
         "sha256_cert_fingerprints": ["AA:BB:CC:..."]
       }
     }
   ]

3. If file verified and fingerprint matches app → launch app with deep link
4. Else → open in browser

5. App receives link and routes to product detail screen
```

## Handling Deferred Deep Links (Pre-Install)

```kotlin
// Android: Store deep link for processing after login/setup
class MainActivity : AppCompatActivity() {
  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    
    val intent = intent
    val deepLink = intent.data  // Deep link URI
    
    if (deepLink != null && !isUserLoggedIn()) {
      // User not logged in yet; save link for after login
      SavedStateHandle.set("deferred_deep_link", deepLink)
      
      // Navigate to login
      startActivity(Intent(this, LoginActivity::class.java))
    } else if (deepLink != null) {
      // User logged in; handle link
      handleDeepLink(deepLink)
    }
  }
}

// After login completes
class LoginActivity : AppCompatActivity() {
  fun onLoginSuccess() {
    val deferredLink = SavedStateHandle.get("deferred_deep_link")
    
    val intent = Intent(this, MainActivity::class.java)
    intent.data = deferredLink
    startActivity(intent)
  }
}
```

## Parsing Deep Links Safely

```swift
func handleDeepLink(_ url: URL) {
  guard let components = URLComponents(url: url, resolvingAgainstBaseURL: true),
        let host = components.host else {
    showError("Invalid deep link")
    return
  }
  
  switch host {
  case "myapp.com":
    if let pathComponents = url.pathComponents.dropFirst() as? [String] {
      switch (pathComponents.first, pathComponents.dropFirst().first) {
      case ("products", let productId?):
        // Validate product ID (prevent injection)
        guard productId.allSatisfy({ $0.isNumber }) else {
          showError("Invalid product ID")
          return
        }
        navigateToProduct(productId)
        
      case ("categories", let categoryId?):
        navigateToCategory(categoryId)
        
      default:
        showError("Unknown deep link: \(url)")
      }
    }
    
  default:
    showError("Unsupported domain: \(host)")
  }
}
```

## When to Use

✓ **Marketing campaigns** (QR codes, email links, social)
✓ **Sharing features** (share product link → deep link)
✓ **Cross-app integration** (calendar apps opening event details)
✓ **Referral programs** (invitation links)

## Production Gotchas

**1. Deferred Deep Link Race Condition**
- User installs app; deep link processed before UI fully ready
- Crash or blank screen
- **Fix:** Delay deep link processing; wait for UI initialization

```swift
func handleDeferredDeepLink() {
  DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
    if let deferredLink = self.getDeferredLink() {
      self.navigateToScreen(deferredLink)
    }
  }
}
```

**2. Deep Link Validation Not Enforced**
- Malformed deep link ("products/abc") crashes
- **Fix:** Validate all components; fail gracefully

**3. Back Stack Corruption**
- Deep link navigation outside normal flow
- Back button behaves unexpectedly
- **Fix:** Use `Intent.FLAG_ACTIVITY_NEW_TASK | FLAG_ACTIVITY_SINGLE_TOP` (Android) or proper navigation stack management (iOS)

---

**Bağlantılar:**
- [[hamle7-mobile-001-mvvm-viewmodel]] (handling navigation in ViewModel)
- [[hamle6-security-004-rate-limiting-distributed]] (preventing link abuse)
- [[hamle6-testing-001-test-pyramid]] (testing deep link scenarios)
