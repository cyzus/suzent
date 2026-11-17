# Rhino's bean JSON converter references java.beans, which Android does not ship.
# That converter runs only when a Java bean is serialized. The bot host evaluates
# the animation bundle and never takes that path.
-dontwarn java.beans.**

# The bytecode optimizer links through jdk.dynalink (removed from the JDK, absent
# on Android). The host forces the interpreter (optimizationLevel = -1), so this
# code is never initialized.
-dontwarn jdk.dynalink.**

# Rhino resolves parts of the interpreter reflectively. Leave its names intact.
-keep class org.mozilla.javascript.** { *; }
