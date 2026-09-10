---
type: decision
title: MVVM with ViewModel Lifecycle Management
category: Mobile Development & Architecture
status: active
created: 2026-08-28
source: mobile-production-systems (Hamle 7)
tags: [mobile, mvvm, viewmodel, lifecycle, state-management]
---

# MVVM with ViewModel Lifecycle

**Pattern:** Separating UI logic from business logic while surviving lifecycle rotations.

## The Problem

Screen rotations (portrait ↔ landscape) destroy and recreate Activities/ViewControllers:
- Network request in progress → view destroyed → view recreated → request completes → crash (null reference)
- Local state lost on rotation
- Multiple network requests triggered (one per rotation)

## Solution: ViewModels (Android) & Observable Patterns (iOS)

**Android: ViewModel survives recreation**

```kotlin
class UserProfileViewModel : ViewModel() {
  // Data holders
  private val _userState = MutableLiveData<UserState>()
  val userState: LiveData<UserState> = _userState
  
  private val _isLoading = MutableLiveData(false)
  val isLoading: LiveData<Boolean> = _isLoading
  
  // Business logic
  fun loadUser(userId: String) {
    _isLoading.value = true
    viewModelScope.launch {
      try {
        val user = userRepository.getUser(userId)
        _userState.value = UserState.Success(user)
      } catch (e: Exception) {
        _userState.value = UserState.Error(e.message)
      } finally {
        _isLoading.value = false
      }
    }
  }
  
  // Survives configuration changes; viewModelScope auto-cancels on clear
  override fun onCleared() {
    super.onCleared()
    // Optional cleanup
  }
}

// Activity: Binds to ViewModel
class UserProfileActivity : AppCompatActivity() {
  private val viewModel: UserProfileViewModel by viewModels()
  
  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    
    // ViewModel survives rotation; same instance
    viewModel.userState.observe(this) { state ->
      when (state) {
        is UserState.Success -> updateUI(state.user)
        is UserState.Error -> showError(state.message)
      }
    }
    
    // Load user (only once per ViewModel creation, not per rotation)
    viewModel.loadUser(intent.getStringExtra("user_id")!!)
  }
}
```

**iOS: @StateObject survives view recreation**

```swift
class UserProfileViewModel: ObservableObject {
  @Published var user: User?
  @Published var isLoading = false
  @Published var errorMessage: String?
  
  func loadUser(userId: String) {
    isLoading = true
    Task {
      do {
        user = try await userRepository.getUser(userId)
      } catch {
        errorMessage = error.localizedDescription
      }
      isLoading = false
    }
  }
}

struct UserProfileView: View {
  @StateObject var viewModel = UserProfileViewModel()
  
  var body: some View {
    VStack {
      if viewModel.isLoading {
        ProgressView()
      } else if let user = viewModel.user {
        Text(user.name)
      } else if let error = viewModel.errorMessage {
        Text("Error: \(error)")
      }
    }
    .onAppear {
      viewModel.loadUser(userId: "123")
    }
  }
}
```

## When to Use

✓ **Any screen with business logic** (network, database, computations)
✓ **Configuration changes** (rotations, theme changes)
✓ **Screen state preservation** (scrolling position, form values)

✗ **Simple static views** (display-only, no state)

## Production Gotchas

**1. ViewModel Holding UI References**
```kotlin
// ❌ Wrong: Memory leak on Activity destruction
class UserViewModel : ViewModel() {
  private val activity: Activity = context.activity  // Wrong!
}

// ✓ Correct: Use Application context only
class UserViewModel : ViewModel() {
  private val context: Context = app.applicationContext
}
```

**2. viewModelScope vs lifecycleScope Timing**
- viewModelScope cancels on ViewModel.onCleared()
- lifecycleScope cancels on Activity.onDestroy()
- Mismatch can cause: Task cancelled mid-way

```kotlin
// ✓ Correct: Use viewModelScope in ViewModel
viewModel.viewModelScope.launch {
  val data = repository.load()  // Survives rotation
}
```

**3. Shared ViewModels Across Fragments**
```kotlin
// ❌ Shared ViewModel: unexpected state sharing
class FragmentA : Fragment() {
  private val sharedViewModel: SharedVM by activityViewModels()
  // onViewCreated -> sharedViewModel.updateCounter()
}

class FragmentB : Fragment() {
  private val sharedViewModel: SharedVM by activityViewModels()
  // Sees counter updated by FragmentA (correct for some use cases, wrong for others)
}

// ✓ Scoped ViewModel: Fragment-only state
class FragmentA : Fragment() {
  private val viewModel: FragmentAVM by viewModels()
  // Self-contained state; no leakage
}
```

---

**Bağlantılar:**
- [[hamle7-mobile-002-redux-async-middleware]] (managing complex async workflows)
- [[hamle6-testing-001-test-pyramid]] (unit testing ViewModels)
- [[hamle5-frontend-004-render-optimization]] (preventing unnecessary re-renders)
