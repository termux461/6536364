package hev.htproxy

/**
 * Must live at exactly this package/class name. The native library's JNI_OnLoad (see
 * heiher/hev-socks5-tunnel src/hev-jni.c) hardcodes FindClass("hev/htproxy/TProxyService")
 * before calling RegisterNatives - any other package or class name here makes FindClass throw
 * ClassNotFoundException, which CheckJNI treats as a fatal JNI protocol violation and aborts the
 * whole process the instant the native library loads. Confirmed via a real device bugreport:
 * "JNI DETECTED ERROR IN APPLICATION: JNI RegisterNatives called with pending exception
 * java.lang.ClassNotFoundException: Didn't find class "hev.htproxy.TProxyService"".
 */
object TProxyService {

    init {
        System.loadLibrary("hev-socks5-tunnel")
    }

    @JvmStatic
    external fun TProxyStartService(configPath: String, fd: Int)

    @JvmStatic
    external fun TProxyStopService()

    @JvmStatic
    external fun TProxyGetStats(): LongArray?
}
