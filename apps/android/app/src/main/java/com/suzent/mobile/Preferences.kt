package com.suzent.mobile

import android.app.LocaleManager
import android.content.Context
import android.content.res.Configuration
import android.os.Build
import android.os.LocaleList
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density

enum class AppearancePreference { SYSTEM, LIGHT, DARK }

/** Multiplies the system font scale, so accessibility sizes keep growing from the chosen step. */
enum class TextSizePreference(val scale: Float) { SYSTEM(1f), SMALL(0.9f), LARGE(1.15f), EXTRA_LARGE(1.3f) }

enum class LanguagePreference(val tag: String?) { SYSTEM(null), ENGLISH("en"), CHINESE("zh-CN") }

/** Phone-only display preferences; nothing here reaches the desktop. */
object AppPreferences {
    private const val FILE = "app_preferences"
    private var store: android.content.SharedPreferences? = null

    private val appearanceState = mutableStateOf(AppearancePreference.SYSTEM)
    private val textSizeState = mutableStateOf(TextSizePreference.SYSTEM)
    private val hapticsState = mutableStateOf(true)

    var appearance: AppearancePreference
        get() = appearanceState.value
        set(value) { appearanceState.value = value; store?.edit()?.putString("appearance", value.name)?.apply() }
    var textSize: TextSizePreference
        get() = textSizeState.value
        set(value) { textSizeState.value = value; store?.edit()?.putString("text_size", value.name)?.apply() }
    var haptics: Boolean
        get() = hapticsState.value
        set(value) { hapticsState.value = value; store?.edit()?.putBoolean("haptics", value)?.apply() }

    fun load(context: Context) {
        val preferences = context.getSharedPreferences(FILE, Context.MODE_PRIVATE).also { store = it }
        appearanceState.value = enumValueOrNull<AppearancePreference>(preferences.getString("appearance", null)) ?: AppearancePreference.SYSTEM
        textSizeState.value = enumValueOrNull<TextSizePreference>(preferences.getString("text_size", null)) ?: TextSizePreference.SYSTEM
        hapticsState.value = preferences.getBoolean("haptics", true)
    }

    /** Per-app language is a platform setting from Android 13; older versions follow the system language. */
    val supportsLanguage: Boolean get() = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU

    fun language(context: Context): LanguagePreference {
        if (!supportsLanguage) return LanguagePreference.SYSTEM
        val locales = context.getSystemService(LocaleManager::class.java).applicationLocales
        if (locales.isEmpty) return LanguagePreference.SYSTEM
        return if (locales[0].language == "zh") LanguagePreference.CHINESE else LanguagePreference.ENGLISH
    }

    fun setLanguage(context: Context, value: LanguagePreference) {
        if (!supportsLanguage) return
        context.getSystemService(LocaleManager::class.java).applicationLocales =
            value.tag?.let { LocaleList.forLanguageTags(it) } ?: LocaleList.getEmptyLocaleList()
    }

    private inline fun <reified T : Enum<T>> enumValueOrNull(name: String?): T? =
        enumValues<T>().firstOrNull { it.name == name }
}

/** Applies the appearance and text size preferences beneath the theme, so every `isSystemInDarkTheme` follows them. */
@Composable
fun AppPreferencesProvider(content: @Composable () -> Unit) {
    val configuration = LocalConfiguration.current
    val density = LocalDensity.current
    val night = when (AppPreferences.appearance) {
        AppearancePreference.SYSTEM -> configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK
        AppearancePreference.LIGHT -> Configuration.UI_MODE_NIGHT_NO
        AppearancePreference.DARK -> Configuration.UI_MODE_NIGHT_YES
    }
    val adjusted = Configuration(configuration).apply { uiMode = (uiMode and Configuration.UI_MODE_NIGHT_MASK.inv()) or night }
    CompositionLocalProvider(
        LocalConfiguration provides adjusted,
        LocalDensity provides Density(density.density, density.fontScale * AppPreferences.textSize.scale),
        content = content,
    )
}
