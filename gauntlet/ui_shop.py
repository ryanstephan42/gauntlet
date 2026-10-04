import pygame

from .economy import Shop


def run_shop(screen, game, points):
    """Returns (purchased_items, remaining_points, start_match)."""
    font = pygame.font.Font(None, 36)
    shop = Shop(game.get("shop", []), points)
    clock = pygame.time.Clock()
    while True:
        screen.fill((30, 30, 40))
        screen.blit(font.render(f"SHOP: {game['meta']['name']}", True, (255, 215, 0)), (50, 50))
        screen.blit(font.render(f"Your Points: {shop.points}", True, (255, 255, 255)), (50, 90))
        y = 150
        for i, item in enumerate(shop.items):
            bought = shop.is_bought(item)
            color = (0, 255, 0) if bought else (255, 255, 255) if shop.can_buy(item) else (200, 200, 200)
            text = f"{i + 1}. {item['name']} ({item['cost']} pts) - {item.get('description', '')}"
            if bought:
                text += " [BOUGHT]"
            screen.blit(font.render(text, True, color), (50, y))
            y += 50
        footer = font.render("Press Number to Buy, SPACE to Start, ESC to Cancel",
                             True, (100, 100, 255))
        screen.blit(footer, (50, screen.get_height() - 60))
        pygame.display.flip()
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                return [], points, False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    return shop.purchased, shop.points, True
                if pygame.K_1 <= event.key <= pygame.K_9:
                    shop.buy(event.key - pygame.K_1)
