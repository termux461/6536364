# --- LC VPN production ProGuard/R8 rules ---
-keepattributes *Annotation*, Signature, InnerClasses, EnclosingMethod

# Room entities are (de)serialized reflectively by column name.
-keep class com.lizercool.lcvpn.data.db.entity.** { *; }

# JNI: hev-socks5-tunnel's native lib calls FindClass("hev/htproxy/TProxyService")
# and RegisterNatives against it. R8 must NOT rename/remove this class or its methods,
# or the native load aborts the process (CheckJNI ClassNotFoundException).
-keep class hev.htproxy.** { *; }

# gomobile / AndroidLibXrayLite bindings are reached from Go via JNI - keep them intact.
-keep class libv2ray.** { *; }
-keep class go.** { *; }

# Anything with native methods (belt-and-suspenders for the above).
-keepclasseswithmembernames class * {
    native <methods>;
}

# kotlinx.serialization: keep generated serializers and @Serializable metadata.
-keepclassmembers @kotlinx.serialization.Serializable class ** {
    *** Companion;
    kotlinx.serialization.KSerializer serializer(...);
}
-keepclasseswithmembers class ** {
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class com.lizercool.lcvpn.**$$serializer { *; }
-keepclassmembers class com.lizercool.lcvpn.** {
    *** Companion;
}

# OkHttp / Okio (used by subscription fetch + ping) - suppress benign warnings.
-dontwarn okhttp3.**
-dontwarn okio.**
-dontwarn org.conscrypt.**
