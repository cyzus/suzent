import SwiftUI
import SuzentCore

struct SuzentSegmentedTabs<Selection: Hashable>: View {
    let options: [Selection]
    @Binding var selection: Selection
    var enabled = true
    let title: (Selection) -> LocalizedStringKey
    @Namespace private var slider
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack(spacing: 0) {
            ForEach(options, id: \.self) { option in
                let selected = selection == option
                Button {
                    withAnimation(reduceMotion ? nil : .easeOut(duration: 0.3)) { selection = option }
                } label: {
                    Text(title(option)).suzentFont(PresentationTokens.typeCaption, weight: selected ? .semibold : .regular)
                        .lineLimit(1).minimumScaleFactor(0.8)
                        .foregroundStyle(selected ? Color.suzentTabBlockText : Color.suzentMuted)
                        .frame(maxWidth: .infinity, minHeight: 40)
                        .background {
                            if selected { Rectangle().fill(Color.suzentTabBlock).matchedGeometryEffect(id: "selection", in: slider) }
                        }
                        .contentShape(Rectangle())
                }.buttonStyle(.plain).disabled(!enabled)
                    .accessibilityAddTraits(selected ? [.isSelected, .isButton] : .isButton)
            }
        }.padding(3).background(Color.suzentTabTrack)
            .overlay(Rectangle().strokeBorder(Color.suzentOutline, lineWidth: 1))
            .opacity(enabled ? 1 : PresentationTokens.disabledAlpha)
            .dynamicTypeSize(...DynamicTypeSize.accessibility2)
    }
}
