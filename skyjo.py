from fpdf import FPDF
from fpdf.pattern import LinearGradient, RadialGradient

class CardPDF(FPDF):
    def add_card(self, x, y, w, h, number, color):
        gradient = RadialGradient(
            self,
            start_circle_x=x + w/2,
            start_circle_y=y + h/2,
            start_circle_radius=0,
            end_circle_x=x + w/2,
            end_circle_y=y + h/2,
            end_circle_radius=(h**2+w**2)**0.5*0.6,
            colors=[(255, 255, 255), color],
        )

        with self.use_pattern(gradient):
            with self.local_context(line_width=0.3):
                # Draw the rectangle for the card
                self.rect(x, y, w, h, "DF")

        font_style = "U" if number in (6, 9) else ""

        for mode in ("stroke", "fill"):
            with self.local_context(font_family="PT Serif", font_style=font_style, font_size=w*0.8, draw_color=(255, 255, 255), text_mode=mode):
                # Add the number in the center
                self.set_xy(x, y + h / 2 - 8)  # Adjust for centering
                self.cell(w, 16, str(number), align='C')

        for mode in ("stroke", "fill"):
            with self.local_context(font_family="PT Serif", font_style=font_style, font_size=w*0.2, draw_color=(255, 255, 255), line_width=w * 0.025 * self.k, text_mode=mode):
                # Add the number on the edges
                self.set_xy(x + 2, y + 2)
                self.cell(w - 4, None, str(number), align='L')  # Top left

                self.set_xy(x + 2, y + 2)
                with self.rotation(180, x + w/2, y + h/2):
                    self.cell(w - 4, None, str(number), align='L')  # Bottom left

    def add_card_back(self, x, y, w, h):
        diagonal_length = (w**2 + h**2)**0.5 / 2**0.5
        start_x = x
        start_y = y + h
        gradient = LinearGradient(
            self,
            from_x=start_x,
            from_y=start_y,
            to_x=start_x + diagonal_length,
            to_y=start_y - diagonal_length,
            colors=["#ff0000", "#ffa500", "#ffff00", "#008000", "#0000ff", "#4b0082", "#ee82ee", "#ff0000"],
            extend_before=True,
            extend_after=True,
        )

        with self.use_pattern(gradient):
            with self.local_context(line_width=0.3):
                # Draw the rectangle for the card back
                self.rect(x, y, w, h, "DF")

        for mode in ("stroke", "fill"):
            with self.local_context(font_family="PT Serif", font_size=w*0.3, draw_color=(255, 255, 255), line_width=w * 0.08 * self.k, text_mode=mode):
                # Add the text in the center
                self.set_xy(x, y + h / 2 - 8)  # Adjust for centering
                self.cell(w, 16, "Skyjo", align='C')

def generate_pdf():
    pdf = CardPDF()
    pdf.set_auto_page_break(auto=False)
    pdf.set_margin(5)
    pdf.add_font("PT Serif", fname="PTSerif-Regular.ttf")

    # Define margins and card grid dimensions
    margin = 5  # mm
    grid_x = 5
    grid_y = 5
    card_w = pdf.epw / grid_x
    card_h = pdf.eph / grid_y

    # pdf.set_text_color(0, 0, 0)  # White outline
    # pdf.set_draw_color(255, 255, 255)  # Black fill
    pdf.set_line_width(card_w * 0.1 * pdf.k)

    pdf.add_page()

    # Define card counts
    cards = (
        [-2] * 5 +
        [-1] * 10 +
        [0] * 15 +
        [num for num in range(1, 13) for _ in range(10)]
    )

    colors = [(40, 53, 147)] * 2 + [(41, 182, 246)] * 1 + [(76, 175, 80)] * 4 + [(255, 235, 59)] * 4 + [(229, 57, 53)] * 4

    # Add cards to pages
    card_index = 0
    while card_index < len(cards):
        for row in range(grid_y):
            for col in range(grid_x):
                if card_index >= len(cards):
                    break
                x = margin + col * card_w
                y = margin + row * card_h
                pdf.add_card(x, y, card_w, card_h, cards[card_index], colors[cards[card_index] + 2])
                card_index += 1
        if card_index < len(cards):
            pdf.add_page()

    pdf.add_page()

    # Add card backs to pages
    card_index = 0
    while card_index < len(cards):
        for row in range(grid_y):
            for col in range(grid_x):
                if card_index >= len(cards):
                    break
                x = margin + col * card_w
                y = margin + row * card_h
                pdf.add_card_back(x, y, card_w, card_h)
                card_index += 1
        if card_index < len(cards):
            pdf.add_page()

    # Save the PDF
    pdf.output("skyjo.pdf")

if __name__ == "__main__":
    generate_pdf()
