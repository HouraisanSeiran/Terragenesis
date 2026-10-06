package com.remotemountains.watershed;

import com.remotemountains.core.Terrain;
import com.remotemountains.core.TerrainScale;
import java.awt.BasicStroke;
import java.awt.Color;
import java.awt.Font;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.imageio.ImageIO;

/** Writes a labelled algorithm preview directly from the source, without game rendering. */
public final class WatershedPreview {
    public static void main(String[] args) throws Exception {
        var source = new WatershedTerrainSource(20260927L, "");
        int width = 960, height = 580;
        BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        double[][] elevations = new double[height][width];
        boolean[][] river = new boolean[height][width];
        boolean[][] sea = new boolean[height][width];
        for (int py = 0; py < height; py++) for (int px = 0; px < width; px++) {
            double x = -160 + px * 2.10, z = -530 + py * 1.83;
            Terrain.Column column = source.sample(x, z);
            double world = TerrainScale.TALL.height(column.height());
            elevations[py][px] = world;
            river[py][px] = Double.isFinite(column.water()) && column.height() >= 72;
            sea[py][px] = Double.isFinite(column.water()) && column.height() < 72;
        }
        for (int py = 0; py < height; py++) for (int px = 0; px < width; px++) {
            double world = elevations[py][px];
            int r, g, b;
            if (sea[py][px]) {
                r = 36; g = 91; b = 143;
            } else if (river[py][px]) {
                r = 37; g = 122; b = 175;
            } else {
                double t = Math.max(0, Math.min(1, (world - 62) / 730));
                double dx = elevations[py][Math.min(width - 1, px + 2)]
                    - elevations[py][Math.max(0, px - 2)];
                double dz = elevations[Math.min(height - 1, py + 2)][px]
                    - elevations[Math.max(0, py - 2)][px];
                double shade = Math.max(.5, Math.min(1.28, .94 + .045 * (dx + dz)));
                r = (int) Math.min(255, (51 + 166 * t) * shade);
                g = (int) Math.min(255, (105 + 110 * t) * shade);
                b = (int) Math.min(255, (63 + 121 * t) * shade);
            }
            image.setRGB(px, py, new Color(r, g, b).getRGB());
        }
        Graphics2D g = image.createGraphics();
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        g.setColor(new Color(255, 255, 255, 225));
        g.setStroke(new BasicStroke(2));
        for (var node : source.graph().nodes()) if (node.visible() && node.downstream() >= 0) {
            var next = source.graph().nodes().get(node.downstream());
            g.drawLine((int) ((node.x() + 160) / 2.10), (int) ((node.z() + 530) / 1.83),
                (int) ((next.x() + 160) / 2.10), (int) ((next.z() + 530) / 1.83));
        }
        g.setFont(new Font("SansSerif", Font.BOLD, 13));
        mark(g, "Peak", source.peak().x(), source.peak().z(), 160, 530);
        for (int i = 0; i < 3; i++) {
            var node = source.graph().source(i);
            mark(g, "Source " + (i + 1), node.x(), node.z(), 160, 530);
        }
        var confluence = source.graph().baselineNode(19 * DrainageGraph.ROWS + 12);
        mark(g, "Confluence", confluence.x(), confluence.z(), 160, 530);
        var bank = source.graph().nearestChannel(900, 0);
        mark(g, "Bank cliff", 900, bank.z() + 96, 160, 530);
        mark(g, "Mouth", source.graph().outlet().x(), source.graph().outlet().z(), 160, 530);
        g.setColor(new Color(10, 31, 47, 220));
        g.fillRoundRect(15, 14, 450, 57, 12, 12);
        g.setColor(Color.WHITE);
        g.setFont(new Font("SansSerif", Font.BOLD, 18));
        g.drawString("Watershed algorithm preview", 27, 39);
        g.setFont(new Font("SansSerif", Font.PLAIN, 13));
        g.drawString("Elevation + modeled channels; not a game screenshot", 27, 58);
        g.dispose();
        Path out = Path.of("preview/watershed/map.png");
        Files.createDirectories(out.getParent());
        ImageIO.write(image, "png", out.toFile());
        System.out.println(out.toAbsolutePath());
    }

    private static void mark(Graphics2D g, String label, double x, double z,
                             double originX, double originZ) {
        int px = (int) ((x + originX) / 2.10), py = (int) ((z + originZ) / 1.83);
        g.setColor(new Color(7, 34, 49, 230));
        g.fillOval(px - 4, py - 4, 8, 8);
        g.drawString(label, px + 7, py - 7);
        g.setColor(Color.WHITE);
        g.fillOval(px - 2, py - 2, 4, 4);
    }
}
