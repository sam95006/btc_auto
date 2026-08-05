# ProGuard / R8 rules for NEXUS Public mobile — NON_SUBMISSION
-keepattributes SourceFile,LineNumberTable
-keepattributes Signature,*Annotation*

# Keep public API DTO models if reflection-based serialization is used later
-keep class com.nexus.public.decision.dto.** { *; }

# Do not obfuscate BuildConfig flags used by hard-ban gates
-keepclassmembers class **.BuildConfig {
    public static final boolean SUBMISSION_AUTHORIZED;
    public static final boolean LIVE_BILLING_ENABLED;
    public static final boolean REAL_IAP_PRODUCTS_ENABLED;
    public static final boolean REVIEW_DEMO_ALLOWED;
}
